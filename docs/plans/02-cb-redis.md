# Plan 02 — Circuit Breaker 状态搬 Redis

> 优先级：🔥🔥
> 性质：**正确性**（多 worker 下熔断逻辑当前是失效的）
> 影响面：router `services/inference_client.py`，**外加** 4 个服务共有的 `common/internal.py:_CIRCUIT_BREAKERS`
> 预计工作量：1.5-2 人日
> 风险：中（涉及失败模式、Redis 不可达时的退化路径）

---

## 1. 现状

### 1.1 当前有两个独立的 CB 系统

#### CB-A：`InferenceClient` 内置 CB
位置：`services/router-service/src/services/inference_client.py:49-77`

```python
self._cb_failures = 0          # 进程级 int
self._cb_open_until: float = 0.0  # 进程级 timestamp
```

阈值/冷却：通过 `__init__` 参数传入，默认 `threshold=3, cooldown=30s`，由环境变量 `INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD/COOLDOWN_SECONDS` 控制。

#### CB-B：`common/internal.py` 全局字典
位置：4 个服务各有一份 vendored copy，例如 `services/router-service/src/common/internal.py:71-77`

```python
@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    opened_until: float | None = None

_CIRCUIT_BREAKERS: dict[str, _CircuitState] = {}  # key = f"{target_service}|{base_url}"
```

被 `request_internal_json` 在 `common/internal.py:347` 检查、`:368/:388/:413` 记录失败、`:382/:400/:409` 记录成功。

### 1.2 多 worker 下的失效场景

router-service 起 4 worker，inference-service 真正不可用时：

```
T=0   worker-1 第 1 次失败   cb_failures=1（worker-1）
T=0.1 worker-2 第 1 次失败   cb_failures=1（worker-2）
T=0.2 worker-3 第 1 次失败   cb_failures=1（worker-3）
T=0.3 worker-4 第 1 次失败   cb_failures=1（worker-4）
T=1.0 worker-1 第 2 次失败 → 第 3 次失败 → CB-1 open
T=...                        CB-2/3/4 各自再独立累计 3 次
```

最少 4×3 = 12 次失败请求才能让 4 个 worker 全部熔断；考虑 `max_retries=1` 的内部重试，实际穿透到 inference-service 的失败请求 = 12 × 2 = **24 次**。

### 1.3 现有 Redis 基础设施可复用

router-service 已经有：
- `aioredis.from_url(settings.ROUTER_REDIS_URL, decode_responses=True)` 在 `main.py:90`
- Redis 不可达时静默降级 `_redis_conn = None`（`main.py:93-95`）
- Lua 脚本注册先例：`rate_limiter.py:65-66`（`register_script(...)`）
- 全局获取：`get_redis()` in `core/dependencies.py:92`

admin/user/inference 当前**没有** Redis 连接（按需新增）。

---

## 2. 目标

1. **多 worker 共享 CB 状态**——任一 worker 的失败计数对所有 worker 可见
2. **原子计数 + 原子 open**——避免竞态导致计数错乱或 cooldown 时间被覆盖
3. **退化路径**——Redis 不可达时回退到当前的进程级 CB（不影响可用性）
4. **接口签名不变**——调用方零感知
5. **范围控制**——本轮先做 router-service 两个 CB；admin/user/inference 的 `common/internal.py` CB 视优先级再排（它们多 worker 数较少，问题不严重）

---

## 3. 设计

### 3.1 Redis Key 设计

```
cb:{service}:{target}:fails       INCR + EXPIRE，TTL = cooldown × 2
cb:{service}:{target}:open_until  Unix timestamp（秒），TTL = cooldown
```

例：
- `cb:router:inference|http://inference:8004:fails`
- `cb:router:inference|http://inference:8004:open_until`

### 3.2 三个原子操作

#### Op 1：检查 + 记录失败（失败发生时）
```lua
-- KEYS[1]=fails_key, KEYS[2]=open_until_key
-- ARGV[1]=threshold, ARGV[2]=cooldown_seconds, ARGV[3]=now
local fails = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], math.ceil(tonumber(ARGV[2]) * 2))
if fails >= tonumber(ARGV[1]) then
    local open_until = tonumber(ARGV[3]) + tonumber(ARGV[2])
    redis.call('SET', KEYS[2], open_until, 'EX', math.ceil(tonumber(ARGV[2])))
    return {fails, open_until}
end
return {fails, 0}
```

#### Op 2：检查熔断状态（每次请求前）
```lua
-- KEYS[1]=open_until_key
-- ARGV[1]=now
local v = redis.call('GET', KEYS[1])
if v == false then return 0 end
local open_until = tonumber(v)
if open_until <= tonumber(ARGV[1]) then
    redis.call('DEL', KEYS[1])
    return 0
end
return open_until
```

返回非 0 → 熔断器仍 open，调用方应快速失败。

#### Op 3：记录成功（成功发生时）
```python
# Python 直接调用 Redis，不用 Lua（单 key 操作天然原子）
await redis.delete(fails_key)
# open_until 不主动清——让 Op 2 自然处理或 TTL 过期
```

### 3.3 Python 包装

新建：`services/router-service/src/services/circuit_breaker.py`

```python
class RedisCircuitBreaker:
    def __init__(
        self,
        redis: aioredis.Redis | None,
        *,
        namespace: str,           # e.g. "router:inference"
        threshold: int = 3,
        cooldown_seconds: float = 30.0,
        fallback: ProcessLocalCB | None = None,  # Redis 不可达退化
    ):
        self._redis = redis
        self._namespace = namespace
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._fallback = fallback or ProcessLocalCB(threshold, cooldown_seconds)
        if redis is not None:
            self._record_failure_script = redis.register_script(LUA_RECORD_FAILURE)
            self._check_open_script = redis.register_script(LUA_CHECK_OPEN)

    async def check_open(self) -> bool:
        if self._redis is None:
            return self._fallback.check_open()
        try:
            open_until = await self._check_open_script(
                keys=[self._key("open_until")],
                args=[time.time()],
            )
            return open_until > 0
        except aioredis.RedisError:
            return self._fallback.check_open()

    async def record_failure(self) -> None:
        if self._redis is None:
            self._fallback.record_failure()
            return
        try:
            await self._record_failure_script(
                keys=[self._key("fails"), self._key("open_until")],
                args=[self._threshold, self._cooldown, time.time()],
            )
        except aioredis.RedisError:
            self._fallback.record_failure()

    async def record_success(self) -> None:
        if self._redis is None:
            self._fallback.record_success()
            return
        try:
            await self._redis.delete(self._key("fails"))
        except aioredis.RedisError:
            self._fallback.record_success()

    def _key(self, suffix: str) -> str:
        return f"cb:{self._namespace}:{suffix}"


class ProcessLocalCB:
    """Fallback：保留原有进程级 CB 行为，逻辑等价于现有 InferenceClient._cb_*"""
    def __init__(self, threshold: int, cooldown_seconds: float):
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._open_until = 0.0

    def check_open(self) -> bool:
        if self._failures >= self._threshold and time.monotonic() < self._open_until:
            return True
        if self._failures >= self._threshold and time.monotonic() >= self._open_until:
            self._failures = 0
        return False

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_until = time.monotonic() + self._cooldown

    def record_success(self) -> None:
        self._failures = 0
```

### 3.4 接入 InferenceClient（CB-A）

```python
# services/router-service/src/services/inference_client.py

class InferenceClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        timeout: float = 10.0,
        max_retries: int = 1,
        retry_backoff: float = 0.2,
        circuit_breaker: RedisCircuitBreaker | None = None,  # ← 新增
    ):
        ...
        self._cb = circuit_breaker or RedisCircuitBreaker(
            redis=None,
            namespace=f"router:inference:{base_url}",
            threshold=3,
            cooldown_seconds=30.0,
        )  # 默认走进程级 fallback

    async def classify(self, ...):
        if await self._cb.check_open():
            return ClassifyResult(success=False, error_code="circuit_open", ...)
        try:
            ...
            await self._cb.record_success()
            return ClassifyResult(success=True, ...)
        except (httpx.ConnectError, httpx.TimeoutException, ...):
            ...
            await self._cb.record_failure()
            return ...
```

`main.py:55-66` 在创建 `InferenceClient` 时注入 redis：
```python
inference_client = InferenceClient(
    base_url=settings.INFERENCE_BASE_URL,
    secret=settings.INTERNAL_SECRET,
    timeout=...,
    circuit_breaker=RedisCircuitBreaker(
        redis=_redis_conn,
        namespace=f"router:inference:{settings.INFERENCE_BASE_URL}",
        threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
        cooldown_seconds=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    ),
)
```

注意 lifespan 顺序：`InferenceClient` 创建得在 `_redis_conn` 初始化之后；当前 `main.py:46-66` 在 lifespan 之外创建 `inference_client`，需要重构挪到 lifespan 内（或把 cb 设为可后注入）。

### 3.5 接入 `common/internal.py`（CB-B）

CB-B 是 4 个服务共享的 internal HTTP 工具的 CB。改造规模翻倍——**本轮只做 router-service**，admin/user/inference 列下一轮（它们 worker 少、影响小）。

router-service 改造：
1. 在 `common/internal.py` 新增 `set_redis_circuit_breaker(redis_conn)` 注入点
2. `_CIRCUIT_BREAKERS` 字典保留作 fallback；新加 `_REDIS_CB: RedisCircuitBreaker | None = None`
3. `_check_circuit_open / _record_failure / _record_success` 三个内部函数改成"如果 _REDIS_CB 存在就走它，否则走原 dict"
4. router-service `main.py` lifespan 在 redis 连接成功后调用 `set_redis_circuit_breaker(_redis_conn)`

---

## 4. 改造步骤

### Step 1：新增 `services/circuit_breaker.py`

按 §3.3 实现，含 Lua 脚本常量、`RedisCircuitBreaker` 与 `ProcessLocalCB`。

### Step 2：单测覆盖

- Redis 可用：3 次失败后 `check_open()` → True；30s 后 → False
- Redis 不可达：所有调用走 fallback，行为与现有进程级 CB 等价
- Redis 调用中途抛 `RedisError`：每次都退化到 fallback，不让 RPC 失败影响业务调用

### Step 3：改造 `InferenceClient`

按 §3.4。保留原 `_cb_failures` / `_cb_open_until` 字段作为兼容，但内部委托给 `RedisCircuitBreaker`。

### Step 4：改造 router `common/internal.py`

按 §3.5。在文件顶部加 `_REDIS_CB` 模块级变量与 `set_redis_circuit_breaker` setter；三个内部函数改造。

### Step 5：lifespan 接入

router-service `main.py`：
```python
# lifespan 内，redis 初始化成功之后
if _redis_conn is not None:
    from common.internal import set_redis_circuit_breaker
    set_redis_circuit_breaker(_redis_conn)
```

`InferenceClient` 也需要从 lifespan 外构造改为 lifespan 内构造（或后注入 cb）。

### Step 6：环境变量校验

`.env.example` 已有：
- `INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD=3`
- `INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS=30`

无需新增；但需要文档强调：**生产部署 router-service 时必须配置 `ROUTER_REDIS_URL`**，否则 CB 状态不共享，多 worker 下逻辑等价于改造前。

---

## 5. 验证方案

### 5.1 单元测试

`tests/test_circuit_breaker.py`（新增）：
- 用 `fakeredis` 或 `redis-mock` 跑全套
- Redis OK 路径：阈值/冷却/恢复
- Redis 抛错路径：每个操作都退化到 fallback，不向上抛
- 并发：用 `asyncio.gather` 同时跑 10 个 record_failure，验证 Lua INCR 的原子性（`fails` 最终 = 10）

### 5.2 集成验证

启动 router-service 4 worker + Redis + 一个故意挂掉的 inference-service：
```
请求打 50 次 → 期望前 3 次失败后立即开始返回 circuit_open（而非现在的 12+ 次）
观察 Redis：redis-cli get cb:router:inference:*:fails 在 [3, 4] 之间
30s 后再发 → 期望 1 次试探请求 + 失败 → 回到熔断
```

对比改造前：4 worker 各自打 3 次才熔断，总穿透 12-24 次。

### 5.3 退化路径验证

刻意 stop redis-server 后：
- `RedisCircuitBreaker.check_open` 走 fallback，不抛错
- 每个 worker 退化到独立 CB（即旧行为）
- 日志层面有一条 `redisError` 记录（频次需限流避免日志爆炸）

---

## 6. 回滚方案

- 改造**保留了 `ProcessLocalCB` fallback**——若 Redis 路径出问题，将构造 `RedisCircuitBreaker(redis=None)` 即可强制走 fallback，等价于改造前
- 完全回滚：还原 `inference_client.py` 与 `common/internal.py`，删 `circuit_breaker.py`
- 回滚单元粒度：每 Step 都是一次独立 commit，可分别 revert

---

## 7. 风险与陷阱

| 风险 | 应对 |
|---|---|
| Lua 脚本错误导致 Redis 端 panic | 脚本先在测试环境跑全套；NOSCRIPT 错误时走 EVAL 重新加载 |
| Redis 网络抖动让 CB 误开 | 抖动时走 fallback（per-worker），不会触发误开 |
| `register_script` 在 redis 重启后 SHA 失效 | redis-py 自动 EVAL 重新加载，不需特殊处理 |
| `_REDIS_CB` 模块级单例与测试隔离 | 提供 `reset_redis_circuit_breaker()` 用于 pytest fixture |
| **lifespan 顺序**：InferenceClient 当前在 lifespan 外构造 | 必须搬进 lifespan 内，或把 cb 改为 setter 注入；本轮选 setter 注入更稳 |
| 多 router 实例 namespace 冲突 | namespace 不含 worker_id（设计如此——同 base_url 多 worker 共享 CB 是目标） |
| Redis cooldown 期间所有 worker 都看到 open——是否过严？ | 是预期行为；这正是修复点 |

---

## 8. Definition of Done

- [ ] `services/circuit_breaker.py` 落地（router-service）
- [ ] 单测覆盖三种路径（OK / fallback / 异常退化）
- [ ] `InferenceClient` 接入 `RedisCircuitBreaker`
- [ ] router `common/internal.py` 接入 `RedisCircuitBreaker`（CB-B）
- [ ] router `main.py` lifespan 注入 redis 连接
- [ ] 集成验证：4 worker × inference 挂掉，熔断在 3-4 次失败内全 worker 同步生效
- [ ] 退化验证：Redis 离线后行为等价于改造前
- [ ] 文档：`README.md` / `DEPLOY.md` 强调"生产 router 必须配置 `ROUTER_REDIS_URL`"

---

## 9. 不在本轮范围

- admin / user / inference 的 `common/internal.py` CB 改造（worker 少、问题轻；下一轮再做）
- 半开状态（half-open）支持：当前实现是 cooldown 一过就直接关闭。半开会更平滑但增加复杂度，留作后续优化
