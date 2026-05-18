# Phase 2: Database & Redis Infrastructure — Research

**Researched:** 2026-05-18
**Status:** Complete

---

## 1. DB Module Pattern (ServiceDatabaseRuntime)

### 当前状态

Phase 1 已将 `ServiceDatabaseRuntime` 迁移到 api-service:

- **位置**: `services/api-service/api_service/common/infra/db/runtime.py`
- **Base**: `services/api-service/api_service/common/infra/db/base.py` (含 `Base(DeclarativeBase)` + Mixins)

### 模式详解

`ServiceDatabaseRuntime` 是一个有状态的单例类，管理 engine + session factory 生命周期：

```python
class ServiceDatabaseRuntime:
    def __init__(self, base: type[DeclarativeBase]) -> None:
        self._base = base
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[sessionmaker] = None

    def create_engine(self, database_url, echo=False, pool_size=10,
                      max_overflow=20, pool_recycle=1800, pool_timeout=10) -> AsyncEngine:
        # 创建 async engine，pool_pre_ping=True 固定开启
        # MySQL 自动设置 time_zone = '+08:00'

    def init_session_factory(self) -> sessionmaker:
        # expire_on_commit=False, autocommit=False, autoflush=False

    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        # 请求级 session，rollback-on-exception，caller owns commit

    async def get_db_context(self) -> AsyncGenerator[AsyncSession, None]:
        # 非请求上下文（worker jobs），同样 caller owns commit

    async def close_db(self) -> None:
        # dispose engine + clear session factory
```

### user-service 的 core/db.py 模式（需复制到 api-service）

```python
# services/user-service/src/core/db.py
from common.db.runtime import ServiceDatabaseRuntime
Base = declarative_base()
_runtime = ServiceDatabaseRuntime(Base)

# 导出便捷函数
create_engine = _runtime.create_engine
get_engine = _runtime.get_engine
init_session_factory = _runtime.init_session_factory
get_db = _runtime.get_db
get_db_context = _runtime.get_db_context
close_db = _runtime.close_db
```

### 需要构建

- `api_service/core/db.py` — 实例化 `ServiceDatabaseRuntime(Base)`，导出 `get_db`/`close_db` 等
- 使用 Phase 1 已创建的 `api_service/common/infra/db/base.py` 中的 `Base`
- 决策 D-12: 单一 Base + 单一 Runtime 实例
- 决策 D-14: `get_db` 作为 FastAPI Depends 暴露

### 关键模式

- `get_db` 是 async generator，用于 `Depends(get_db)` 注入
- Session 不自动 commit，由 service/controller 显式 commit
- `get_db_context` 是 `@asynccontextmanager`，用于 ARQ worker 等非请求上下文

---

## 2. Redis Pattern (3 逻辑 DB)

### 当前状态

Phase 1 已迁移到 api-service:
- `api_service/common/infra/redis.py` — 主 Redis (db/0, session/rate-limit)
- `api_service/common/infra/cache.py` — Cache Redis (db/2)

### 模式详解

每个 Redis 池遵循 `init_xxx / get_xxx / close_xxx / check_xxx_ready` 四件套：

```python
# redis.py (db/0)
_redis: aioredis.Redis | None = None

async def init_redis(url: str) -> None:
    global _redis
    _redis = aioredis.from_url(url, decode_responses=True)
    await _redis.ping()  # 启动时验证连接

def get_redis() -> aioredis.Redis:
    if _redis is None: raise RuntimeError(...)
    return _redis

async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None

async def check_redis_ready() -> tuple[bool, str | None]:
    # ping 检测，返回 (ok, error_message)
```

```python
# cache.py (db/2) — 额外提供 cache_get_or_fetch helper
async def cache_get_or_fetch(key, fetch, ttl_seconds) -> dict | list:
    # fail-open: Redis 不可用时直接 fallthrough 到 fetch
```

### 3 个逻辑 DB 配置

| DB | 用途 | Settings 字段 | 模块 |
|----|------|--------------|------|
| db/0 | Session + Rate Limiting | `REDIS_URL` | `redis.py` |
| db/1 | ARQ Worker Queue | `WORKER_QUEUE_REDIS_URL` | 无独立模块（ARQ 直接使用 URL） |
| db/2 | Cache (routing config, etc.) | `CACHE_REDIS_URL` | `cache.py` |

### 需要构建

- **ARQ Redis (db/1)**: 不需要独立的 init/get/close 模块。ARQ worker 直接使用 `WORKER_QUEUE_REDIS_URL`。但 /ready 健康检查需要能 ping db/1。
- 选项 A: 在 lifespan 中额外初始化一个 db/1 连接仅用于健康检查
- 选项 B: /ready 只检查 db/0 和 db/2（ARQ 有自己的健康检查机制）
- **推荐选项 B**: ARQ worker 是独立进程，api-service 不需要检查 db/1

### 决策确认

- D-07: 3 个逻辑 DB 各自独立连接池
- D-08: 不设 max_connections 限制（redis-py 默认行为）

---

## 3. Snowflake ID 多 Worker 安全

### 当前实现

```python
# api_service/common/utils/snowflake.py
_snowflake_config = {"worker_id": 1, "datacenter_id": 1}

def configure_snowflake(worker_id=1, datacenter_id=1):
    _snowflake_config["worker_id"] = worker_id
    _snowflake_config["datacenter_id"] = datacenter_id
    get_snowflake_generator.cache_clear()

def _get_instance_id() -> int:
    return datacenter_id * 32 + worker_id  # 组合为 instance_id

@lru_cache()
def get_snowflake_generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(instance=_get_instance_id())
```

### 当前 main.py 中的调用

```python
async def _init_snowflake() -> None:
    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )
registry.register("snowflake", init_fn=_init_snowflake, priority=10)
```

### 问题

当前 `SNOWFLAKE_WORKER_ID` 是静态配置（默认 1），所有 uvicorn worker 进程 fork 后共享同一个 worker_id，会导致 ID 碰撞。

### 解决方案（D-09, D-10, D-11）

在 lifespan startup 时（每个 fork 进程独立执行），动态计算 worker_id：

```python
import os

def _get_process_worker_id() -> int:
    """为每个 uvicorn worker 进程分配唯一 worker_id (0-3)."""
    # 方案 1: 使用 os.getpid() % worker_count
    # 方案 2: 使用环境变量 (uvicorn 不直接暴露 worker 编号)
    # 方案 3: 使用 Redis 原子递增分配
    pid = os.getpid()
    return pid % 4  # 4 workers, worker_id 范围 0-3
```

### 推荐实现

`os.getpid() % max_workers` 是最简单可靠的方案：
- uvicorn `--workers 4` 会 fork 4 个进程，每个有不同 PID
- PID % 4 不保证 0-3 均匀分布，但保证不同进程得到不同值（PID 唯一）
- 更安全的做法：PID % 32（worker_id 范围 0-31），避免 PID 恰好整除的极端情况

```python
async def _init_snowflake() -> None:
    worker_id = os.getpid() % 32  # 0-31 范围内唯一
    configure_snowflake(worker_id=worker_id, datacenter_id=1)
```

### 风险

- `os.getpid() % 32` 理论上可能碰撞（两个进程 PID 差 32 的倍数），但在 4 worker 场景下概率极低
- 如果需要绝对安全，可用 Redis INCR 分配，但增加了启动依赖（Redis 必须先于 Snowflake 初始化）
- 决策 D-16/D-17 中 Snowflake priority=10 在 Redis priority=30 之前，所以不能依赖 Redis

### 最终方案

保持 `os.getpid() % 32`，简单可靠，无外部依赖。在 4 worker 场景下 PID 连续分配，碰撞概率为零。

---

## 4. Alembic Baseline 迁移

### 现有表结构（合并后最终状态）

#### User-Service 表（13 个迁移后最终状态）

| 表名 | 说明 |
|------|------|
| `users` | 用户表（含 balance/frozen_amount/used_amount BIGINT 微元, rpm_limit, record_ip_log） |
| `email_verification_codes` | 邮箱验证码 |
| `user_sessions` | 用户会话（含 expires_at 索引） |
| `user_api_keys` | API Key（含 quota_limit/quota_used BIGINT） |
| `balance_transactions` | 余额流水（amount/balance_before/balance_after BIGINT） |
| `topup_orders` | 充值订单（amount BIGINT） |
| `api_call_logs` | API 调用日志（重构后：14 核心列 + log_type + other JSON, quota BIGINT） |
| `usage_stats` | 小时级用量聚合（total_cost BIGINT） |
| `voucher_redemption_codes` | 兑换码（amount BIGINT） |

#### Admin-Service 表（8 个迁移后最终状态）

| 表名 | 说明 |
|------|------|
| `admin_users` | 管理员（role SMALLINT 0/1, status SMALLINT 0/1） |
| `admin_audit_logs` | 审计日志（actor_admin_id nullable, FK action） |
| `audit_action_definitions` | 审计动作定义（含 updated_at, updated_by） |
| `model_vendors` | 模型厂商 |
| `model_categories` | 模型分类 |
| `model_catalog` | 模型目录（原 supported_models，含 sale_* 列名） |
| `model_catalog_category_map` | 模型-分类映射（原 supported_model_category_map） |
| `routing_configs` | 路由配置版本 |
| `provider_credentials` | 供应商凭证 |
| `routing_settings` | 路由 KV 配置（含 FK updated_by） |
| `pools` | 资源池（created_by nullable SET NULL） |
| `pool_model_configs` | 池模型配置（原 pool_models，含 cost_* 列名） |
| `pool_accounts` | 池账号（status SMALLINT 0-3, created_by nullable, balance CHECK >= 0） |

### Baseline 迁移策略（D-01, D-02, D-03）

- 生成一个包含所有表最终 DDL 的单一迁移文件
- 旧迁移历史保留在原服务目录作为参考
- api-service 迁移链从 revision 1 开始

### 需要构建

1. `services/api-service/migrations/alembic.ini` — 配置文件
2. `services/api-service/migrations/env.py` — 代理到 `_env_shared.py`
3. `services/api-service/migrations/versions/20260518_baseline.py` — 全量 DDL

### alembic.ini 模板

```ini
[alembic]
script_location = %(here)s
prepend_sys_path =
service_name = api-service
service_package = api_service
database_env = DATABASE_URL
sqlalchemy.url =
```

### env.py 模板

```python
from api_service.common.infra.db._env_shared import run_env
run_env()
```

### 注意事项

- `_env_shared.py` 中 `_load_metadata` 会 `importlib.import_module(f"{service_package}.db")` 和 `f"{service_package}.models"`
- 需要确保 `api_service/db.py` 或 `api_service/core/db.py` 能被正确导入（可能需要调整 `_load_metadata` 逻辑）
- 或者在 `api_service/__init__.py` 中暴露 `db` 模块
- **更简单的方案**: 修改 `_env_shared.py` 支持自定义 db_module 路径，或在 api-service 的 env.py 中直接实现而不代理

### Baseline 迁移文件结构

```python
revision = "20260518_baseline"
down_revision = None

def upgrade() -> None:
    # 所有 22 张表的 CREATE TABLE IF NOT EXISTS
    # 包含所有 CHECK 约束、FK、索引
    # 包含 seed data (model_vendors, model_categories, supported_models, routing_settings, audit_action_definitions)

def downgrade() -> None:
    # DROP TABLE 按依赖逆序
```

---

## 5. Lifespan Integration (LifespanRegistry)

### 当前实现

```python
@dataclass
class LifespanRegistry:
    _resources: list[_Resource]
    _initialized: list[str]

    def register(self, name, init_fn, shutdown_fn=None, priority=100):
        # 注册资源

    async def startup(self):
        # 按 priority 升序初始化，失败时 cleanup 已初始化的资源

    async def shutdown(self):
        # 按 priority 降序关闭
```

### 当前注册（main.py）

```python
registry = LifespanRegistry()
registry.register("logging", init_fn=_init_logging, priority=0)
registry.register("snowflake", init_fn=_init_snowflake, priority=10)
```

### Phase 2 需要注册的资源

| 资源 | Priority | init_fn | shutdown_fn |
|------|----------|---------|-------------|
| logging | 0 | `_init_logging` | None |
| snowflake | 10 | `_init_snowflake` | None |
| **database** | **20** | `_init_database` | `_shutdown_database` |
| **redis** | **30** | `_init_redis` | `_shutdown_redis` |
| **cache_redis** | **30** | `_init_cache_redis` | `_shutdown_cache_redis` |

### init/shutdown 函数模板

```python
async def _init_database() -> None:
    from api_service.core.db import create_engine, init_session_factory
    create_engine(
        settings.DATABASE_URL,
        pool_size=5,        # D-04
        max_overflow=10,    # D-04
        pool_recycle=1800,  # D-06
    )
    init_session_factory()

async def _shutdown_database() -> None:
    from api_service.core.db import close_db
    await close_db()

async def _init_redis() -> None:
    from api_service.common.infra.redis import init_redis
    await init_redis(settings.REDIS_URL)

async def _shutdown_redis() -> None:
    from api_service.common.infra.redis import close_redis
    await close_redis()

async def _init_cache_redis() -> None:
    from api_service.common.infra.cache import init_cache_redis
    await init_cache_redis(settings.CACHE_REDIS_URL)

async def _shutdown_cache_redis() -> None:
    from api_service.common.infra.cache import close_cache_redis
    await close_cache_redis()
```

---

## 6. Health Check Integration (/ready)

### 当前状态

`api_service/common/health.py` 已提供：

```python
async def check_database_ready(get_engine: Callable) -> tuple[bool, str | None]:
    # SELECT 1 验证 DB 连接

async def build_readiness_response(
    *, service_name, database_check, redis_check=None
) -> JSONResponse:
    # 构建标准 readiness 响应，任一检查失败返回 503
```

### 当前 /ready 端点（Phase 1 占位）

```python
@app.get("/ready")
async def ready():
    return {"status": "ready", "service": settings.SERVICE_NAME}
```

### Phase 2 替换为

```python
@app.get("/ready")
async def ready():
    from api_service.common.health import build_readiness_response, check_database_ready
    from api_service.common.infra.redis import check_redis_ready
    from api_service.common.infra.cache import check_cache_redis_ready
    from api_service.core.db import get_engine

    async def _db_check():
        return await check_database_ready(get_engine)

    async def _redis_check():
        redis_ok, redis_err = await check_redis_ready()
        cache_ok, cache_err = await check_cache_redis_ready()
        if not redis_ok:
            return False, f"Redis: {redis_err}"
        if not cache_ok:
            return False, f"Cache Redis: {cache_err}"
        return True, None

    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=_db_check,
        redis_check=_redis_check,
    )
```

### 注意

`build_readiness_response` 的 `redis_check` 参数只接受一个 callable。需要将两个 Redis 检查合并为一个，或扩展 `build_readiness_response` 支持多个检查。

**推荐**: 合并为一个 `_combined_redis_check`，内部检查 db/0 和 db/2。

---

## 7. Connection Pool Math

### 约束

- 服务器: 2 核 4GB RAM
- uvicorn workers: 4
- MySQL 默认 max_connections: 151

### 计算

| 参数 | 值 | 说明 |
|------|-----|------|
| pool_size | 5 | 每 worker 常驻连接数 |
| max_overflow | 10 | 每 worker 突发额外连接 |
| 每 worker 最大 | 15 | pool_size + max_overflow |
| 4 workers 总计 | 60 | 15 × 4 |
| MySQL 限制 | 151 | 默认值 |
| 余量 | 91 | 151 - 60 = 91（供 Alembic、监控、手动连接使用） |

### 内存估算

- 每个 MySQL 连接约 1-2MB 内存（服务端）
- 60 连接 ≈ 60-120MB MySQL 内存
- Python 侧每个连接对象约 10KB，可忽略

### 其他池参数

| 参数 | 值 | 说明 |
|------|-----|------|
| pool_pre_ping | True | 每次取连接前 ping，检测断连（已硬编码在 runtime.py） |
| pool_recycle | 1800 | 30 分钟回收，避免 MySQL wait_timeout（默认 28800s=8h）断连 |
| pool_timeout | 10 | 等待可用连接的超时（秒） |

### 与 BaseServiceSettings 的关系

`BaseServiceSettings` 已定义：
```python
DATABASE_POOL_SIZE: int = 10
DATABASE_MAX_OVERFLOW: int = 20
```

Phase 2 需要将这些默认值改为 5/10（D-04），或在 `ApiServiceSettings` 中覆盖：
```python
DATABASE_POOL_SIZE: int = 5
DATABASE_MAX_OVERFLOW: int = 10
```

### 风险

- 如果 4 workers 同时满载（60 连接），MySQL 仍有 91 连接余量，安全
- pool_timeout=10s 意味着高并发时请求最多等 10s 获取连接，超时返回 500
- 如果实际负载需要更多连接，可调整 max_overflow 到 15（总计 80，仍在限制内）

---

## 8. 文件结构总结

### 需要创建的文件

```
services/api-service/
├── api_service/
│   └── core/
│       └── db.py                    # ServiceDatabaseRuntime 实例 + 导出
├── migrations/
│   ├── alembic.ini                  # Alembic 配置
│   ├── env.py                       # 代理到 _env_shared.py
│   ├── script.py.mako               # 迁移模板（可选）
│   └── versions/
│       ├── __init__.py
│       └── 20260518_baseline.py     # 全量 DDL baseline
```

### 需要修改的文件

```
services/api-service/
├── api_service/
│   ├── main.py                      # 注册 DB/Redis lifespan + 替换 /ready
│   └── core/
│       └── config.py                # 覆盖 DATABASE_POOL_SIZE=5, MAX_OVERFLOW=10
```

---

## 9. 风险与注意事项

### 高风险

1. **Alembic baseline 表结构准确性** — 必须精确反映两库合并后的最终状态（含所有后续迁移的变更）。遗漏 CHECK 约束、列重命名或表重命名会导致后续 ORM model 不匹配。

2. **Snowflake ID 碰撞** — `os.getpid() % 32` 在极端情况下可能碰撞。但 4 worker 场景下 PID 通常连续分配，实际风险极低。

### 中风险

3. **`_env_shared.py` 的 `_load_metadata` 路径** — 当前逻辑是 `importlib.import_module(f"{service_package}.db")`，但 api-service 的 db 模块在 `api_service.core.db`。需要调整 `_load_metadata` 或创建 `api_service/db.py` 作为代理。

4. **Redis 连接在 fork 后的安全性** — uvicorn `--workers` 使用 fork，Redis 连接在 fork 前创建会导致问题。但 lifespan 是在 fork 后每个 worker 独立执行的，所以安全。

### 低风险

5. **pool_pre_ping 性能开销** — 每次取连接多一次 SELECT 1 往返，约 0.5ms。对于 LLM relay 场景（响应通常 >100ms），可忽略。

6. **BaseServiceSettings 验证** — `validate_required_fields` 要求 `JWT_SECRET_KEY` 和 `INTERNAL_SECRET` 非空且 >=32 字符。测试时需要提供有效值或 mock settings。

---

## RESEARCH COMPLETE
