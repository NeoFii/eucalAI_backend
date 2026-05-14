# Plan 01 — httpx 客户端单例化改造

> 优先级：🔥🔥
> 性质：性能 + 鲁棒
> 影响面：4 个服务共有的 `common/internal.py`、admin `pool_service.py`、admin `health_check_service.py`
> 预计工作量：0.5-1 人日
> 风险：低（接口签名不变，行为等价）

---

## 1. 现状

### 1.1 调研出的全部使用点

| 文件 | 行号 | 形式 | 频次 | 现状评价 |
|---|---|---|---|---|
| services/router-service/src/services/inference_client.py | 51 | `httpx.AsyncClient(base_url=..., timeout=httpx.Timeout(timeout))` 在 `__init__` 中实例化 | 每个 chat 请求 1 次 | ✅ 已是单例，但 timeout 是标量、缺 Limits |
| services/router-service/src/common/internal.py | 351 | `async with httpx.AsyncClient(timeout=timeout) as client:` 一次性 | 每次 internal RPC 1 次 | ❌ |
| services/admin-service/src/common/internal.py | 351 | 同上（vendored copy） | 同上 | ❌ |
| services/user-service/src/common/internal.py | 351 | 同上 | 同上 | ❌ |
| services/inference-service/src/common/internal.py | 351 | 同上 | 同上 | ❌ |
| services/admin-service/src/services/pool_service.py | 455, 522 | `async with httpx.AsyncClient(timeout=30) as client:` | 模型池探测 / 连通性测试 | ❌ |
| services/admin-service/src/services/health_check_service.py | 79, 104 | `async with httpx.AsyncClient(timeout=settings.HEALTH_CHECK_TIMEOUT_SECONDS) as client:` | 健康巡检定时任务 | ❌ |

### 1.2 问题

每次 `async with httpx.AsyncClient(...)` 会：
1. 新建 socket → DNS → TCP 三次握手（~0.5ms 同机房，1-3ms 跨可用区）
2. 若上游是 HTTPS，再加 TLS 握手（5-15ms）
3. 退出 `async with` 时关闭连接 → ephemeral port 进入 TIME_WAIT
4. `timeout=10.0` 是标量，意味着 connect / read / write / pool 共用一个超时，**连接池满时无声排队**

router→inference 是每个 chat 请求都走一次的高频内部链路，按上游 HTTPS 计算，这一项每请求至少多 5-15ms p50 延迟，p99 在拥塞时可能更糟。

---

## 2. 目标

1. 进程内**全局复用** `httpx.AsyncClient` 实例（按 `(target, scheme)` 维度区分）
2. 显式分层超时 `httpx.Timeout(connect=..., read=..., write=..., pool=...)`
3. 显式连接池上限 `httpx.Limits(max_connections=..., max_keepalive_connections=...)`
4. 生命周期：lifespan 期创建，shutdown 时 `await client.aclose()`
5. **接口签名不变**——`request_internal_json` 等函数对调用方完全透明

---

## 3. 设计

### 3.1 共享客户端的位置

**方案 A**：放在 `common/http_client.py`，每个服务的 `common/` 都各持一份（与现有 vendored 模式一致）。
- 优点：与现有 `common/` 布局一致，无需跨服务依赖
- 缺点：4 份 copy 维护

**方案 B**：放在 `app.state.http`，通过 FastAPI 依赖注入。
- 优点：FastAPI 原生模式，测试友好
- 缺点：`common/internal.py` 当前是模块级函数（没有 `request: Request` 参数），改动会污染 16 处调用点的签名

✅ **采用 A**：模块级 `common/http_client.py`，提供 `get_http_client()` 与 `init_http_clients()` / `shutdown_http_clients()` 两个 lifecycle 钩子。

### 3.2 客户端粒度

**不**做"每个 base_url 一个 client"——会爆炸。改为**两个共享实例**：

```python
# common/http_client.py（每服务一份 vendored copy，逻辑相同）

_INTERNAL_CLIENT: httpx.AsyncClient | None = None  # 用于 internal-service 调用
_EXTERNAL_CLIENT: httpx.AsyncClient | None = None  # 用于 LLM 上游 / 第三方

def init_http_clients(*, internal_timeout, external_timeout) -> None:
    global _INTERNAL_CLIENT, _EXTERNAL_CLIENT
    _INTERNAL_CLIENT = httpx.AsyncClient(
        timeout=internal_timeout,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
        # 不传 base_url：通过完整 URL 调用
    )
    _EXTERNAL_CLIENT = httpx.AsyncClient(
        timeout=external_timeout,
        limits=httpx.Limits(
            max_connections=200,
            max_keepalive_connections=50,
            keepalive_expiry=30.0,
        ),
    )

async def shutdown_http_clients() -> None:
    if _INTERNAL_CLIENT is not None:
        await _INTERNAL_CLIENT.aclose()
    if _EXTERNAL_CLIENT is not None:
        await _EXTERNAL_CLIENT.aclose()

def get_internal_client() -> httpx.AsyncClient:
    if _INTERNAL_CLIENT is None:
        raise RuntimeError("internal http client not initialized")
    return _INTERNAL_CLIENT

def get_external_client() -> httpx.AsyncClient:
    ...
```

### 3.3 超时分层

```python
# 内部 RPC（admin/user/inference 之间）：低延迟、可重试
INTERNAL_TIMEOUT = httpx.Timeout(
    connect=2.0,   # TCP/TLS 握手必须快
    read=10.0,     # 配合 INTERNAL_HTTP_TIMEOUT_SECONDS
    write=5.0,
    pool=2.0,      # 连接池满时拿不到 → 快速失败而非排队
)

# 外部上游（LLM API）：可能慢
EXTERNAL_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=60.0,     # litellm 已有自己的 timeout=45.0，这里是兜底
    write=10.0,
    pool=2.0,
)
```

> 关键参数：**`pool=2`**。连接池满时若不限制，请求会无声地在内部 asyncio 队列里等连接，表现为整体延迟暴涨而无错误日志。

### 3.4 InferenceClient 特殊化

`router-service/services/inference_client.py:51` 已经是单例。不替换为通用 client，但补充：
- timeout 升级为 `httpx.Timeout(connect=2, read=10, write=5, pool=2)`
- 加 `limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)`
- 保留独立 `AsyncClient` 实例（便于注入 base_url、与通用 client 解耦）

---

## 4. 改造步骤

按文件分组，独立可提交：

### Step 1：建 `common/http_client.py`（4 服务各一份）

新文件：
- `services/router-service/src/common/http_client.py`
- `services/admin-service/src/common/http_client.py`
- `services/user-service/src/common/http_client.py`
- `services/inference-service/src/common/http_client.py`

内容如 §3.2，可用脚本同步保持一致（或后续抽公共仓库）。

### Step 2：改 `common/internal.py:351`（4 服务）

```python
# 改前
async with httpx.AsyncClient(timeout=timeout) as client:
    response = await client.request(method, url, ...)

# 改后
client = get_internal_client()
response = await client.request(
    method,
    url,
    timeout=timeout,  # 调用级覆盖（保持调用方传入的 timeout 语义）
    ...
)
```

注意：保留**调用级 timeout 覆盖**（`client.request(..., timeout=...)`），让 `request_internal_json(timeout=...)` 这个参数继续生效，不破坏现有 API。

### Step 3：改 admin `pool_service.py:455, 522`、`health_check_service.py:79, 104`

同样模式：替换 `async with httpx.AsyncClient(timeout=30)` 为 `get_external_client()` 或 `get_internal_client()`（按目标判断——pool_service 调的是上游 LLM API，应走 external client）。

### Step 4：改 4 个服务的 `main.py` lifespan

```python
# main.py lifespan 起始位置
from common.http_client import init_http_clients, shutdown_http_clients
init_http_clients(
    internal_timeout=INTERNAL_TIMEOUT,
    external_timeout=EXTERNAL_TIMEOUT,
)
yield
await shutdown_http_clients()
```

### Step 5：改 `inference_client.py:51`

```python
self._client = httpx.AsyncClient(
    base_url=self._base_url,
    timeout=httpx.Timeout(connect=2.0, read=timeout, write=5.0, pool=2.0),
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
)
```

---

## 5. 验证方案

### 5.1 单元测试

- 现有 `tests/` 中 `request_internal_json` 的 mock 应继续通过（接口未变）
- 新增 `test_http_client.py`：验证 `init_http_clients` → `get_internal_client` 单例语义、`shutdown_http_clients` 后再次调用抛 RuntimeError

### 5.2 集成验证（本地）

启动 router + inference 服务，对 `/v1/chat/completions` 打 1000 次请求，对比改造前后：
- p50/p95/p99 延迟（期望 p50 ↓5-10ms）
- `ss -tn state time-wait | wc -l`（期望 TIME_WAIT 数显著下降）
- `lsof -p <pid> | grep ESTABLISHED | wc -l`（期望稳定在 keepalive 池容量内）

### 5.3 灰度

第一批：仅改 router-service（影响 router→inference / router→user-service 调用链）
观察 24h：errorRate / latencyP99 / 连接池使用率（需先接 Prometheus 指标，或手工 `httpx` debug 日志）
第二批：扩到 admin / user / inference

---

## 6. 回滚方案

- 改动均为函数体内替换 + 新增模块，**接口签名零变化**
- 回滚 = 还原 `common/internal.py` 与三个 admin 文件即可，`common/http_client.py` 删不删都不影响
- lifespan 钩子若失败：`init_http_clients` 抛错会让 service 启动失败，提早暴露而非生产挂掉

---

## 7. 风险与陷阱

| 风险 | 应对 |
|---|---|
| 测试中模块级 `_INTERNAL_CLIENT` 状态污染 | 提供 `reset_http_clients()` 用于测试，pytest fixture 中调用 |
| 多 worker 下每 worker 各自一个 client（4×100 连接） | 这是预期行为；实际后端连接数 = `workers × max_connections`，需根据上游容量校准；router 4 worker × 100 = 400 上限对 inference-service 无压力 |
| `httpx.AsyncClient` 在 fork 模型下行为？ | uvicorn `--workers` 是 fork 模型，但 `init_http_clients` 在 lifespan（fork 之后）执行，每个 worker 自己创建——OK |
| `keepalive_expiry=30s` 与上游 keepalive timeout 不匹配 | 通常上游 nginx/uvicorn keepalive 默认 75s，本地设短一点更稳；若发现 502 RST 可调小 |
| 调用级 `timeout=` 覆盖能否覆盖到 pool？ | httpx `client.request(timeout=...)` 接受 `httpx.Timeout` 或标量，标量会展开覆盖所有四项；保留传入的标量行为符合现有语义 |

---

## 8. Definition of Done

- [ ] 4 个 `common/http_client.py` 文件落地
- [ ] 4 个 `common/internal.py:351` 改造完成
- [ ] admin 3 处特殊客户端改造完成（`pool_service.py:455/522`、`health_check_service.py:79/104`）
- [ ] router `inference_client.py` Limits + 分层 timeout 升级
- [ ] 4 个服务 lifespan 接入 init/shutdown 钩子
- [ ] 现有单测全绿
- [ ] 本地集成验证：p50 延迟下降 / TIME_WAIT 数下降
- [ ] 文档更新：`README.md` 或 `DEPLOY.md` 标注共享 client 模式
