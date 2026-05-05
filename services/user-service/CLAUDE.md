# User-Service 开发规范

## 项目概述

FastAPI + SQLAlchemy Async + Redis + ARQ Worker 的用户服务微服务，负责认证、计费、API Key 管理、邮箱验证等核心用户域功能。

技术栈：Python 3.10+, FastAPI, SQLAlchemy 2.x (async), Pydantic v2, httpx, Redis, ARQ, MySQL (aiomysql)

## 架构分层

```
Controllers (FastAPI routers, 薄层)
    ↓ Depends(policies) 鉴权
Services (stateless @staticmethod, 业务逻辑)
    ↓
Repositories (BaseRepository[T], 数据访问)
    ↓
ORM Models (SQLAlchemy declarative)
```

跨服务通信：
```
Controllers / Services → Gateways (BaseGateway 子类)
    ↓
common/internal.py (HMAC 签名 + 熔断 + 重试 + 连接池)
```

## 核心规范

### Gateway 层

- 所有 Gateway 必须继承 `common.gateway.base.BaseGateway`
- 在 `__init__` 中声明 `base_url`、`timeout`、`error_map`
- 业务方法直接调用 `self._get()` / `self._post()` / `self._request()`，不要手写 try/except
- Gateway 实例在模块底部作为**模块级单例**创建，消费方 import 单例而非在 handler 内 new
- 需要 graceful fallback 的场景（如 admin-service 不可达时返回 env 默认值），在子类方法中单独 try/except `InternalServiceError`

```python
class MyGateway(BaseGateway):
    def __init__(self) -> None:
        super().__init__(
            "target-service",
            base_url=settings.TARGET_SERVICE_URL,
            timeout=5.0,
            error_map={404: NotFoundException, 422: ValidationException},
        )

    async def get_something(self, id: str) -> dict:
        return await self._get(f"/api/v1/internal/things/{id}")

my_gateway = MyGateway()
```

### HTTP Client

- 禁止在业务代码中 `async with httpx.AsyncClient(...) as client:` 创建临时 client
- 使用 `common.internal.get_internal_client(base_url, timeout=...)` 获取共享连接池 client
- 连接池参数：`max_connections=20, max_keepalive_connections=10`
- 连接池在 `main.py` lifespan shutdown 中通过 `close_internal_clients()` 关闭

### Repository 层

- 继承 `BaseRepository[ModelT]`
- 分页查询优先使用 `self.get_list(ListParams(...), options=[...])` 而非手动 count + offset
- 需要 eager loading 时通过 `options=[selectinload(...)]` 参数传入
- 自定义查询方法仅用于 `get_list` 无法覆盖的复杂场景（JOIN、聚合等）

### Service 层

- 使用 `@staticmethod` + `db: AsyncSession` 作为第一参数
- 方法内部按需实例化 Repository：`UserRepository(db)`
- 事务由 service/controller 显式 `await db.commit()` 控制，`get_db()` 仅提供 rollback-on-exception 安全网
- 幂等操作通过 `ref_id` 去重，余额变更使用 `SELECT ... FOR UPDATE` 行锁

### Controller 层

- 保持薄层，只做参数提取、调用 service、构造 response
- 用户鉴权通过 `Depends(require_active_user)`
- 内部服务鉴权通过 `Depends(verify_internal_secret)`
- 不要在 controller 中直接操作 ORM model 字段（除简单的 status 更新场景）

### 异步规范

- 所有 handler 和 service 方法都是 `async`
- 禁止在 async 上下文中调用阻塞函数（bcrypt、文件 IO、同步 HTTP）
- CPU 密集操作（bcrypt 等）必须使用 `asyncio.to_thread()` 包装的异步版本：
  - `hash_password_async()` / `verify_password_async()` 替代同步版本
  - 同步 `hash_password()` / `verify_password()` 仅用于模块级一次性初始化
- 阻塞 IO（如 SMTP）使用 `await asyncio.to_thread(blocking_fn, ...)`
- 并发 IO 使用 `asyncio.gather()`

### 数据库 Session 生命周期

- `get_db()` 仅提供 rollback-on-exception，不自动 commit
- `get_db_context()` 用于非请求上下文（ARQ worker），同样不自动 commit
- 所有写操作必须显式 `await db.commit()`
- 余额操作使用 `SELECT ... FOR UPDATE` + 显式 commit 保证一致性

### 日志规范

- 模块级 logger：`logger = logging.getLogger(__name__)`
- 结构化日志使用 `log_event(logger, level, "eventName", key=value)`
- 禁止内联 `logging.getLogger("xxx").info(...)` 
- 禁止非结构化 `logger.info("xxx: key=%s", value)` 格式，统一用 `log_event`
- 敏感信息（API key、密码、token）不得出现在日志中，observability 层已有自动脱敏
- 请求上下文（request_id, trace_id, span_id, uid）由 middleware 自动注入，无需手动传递

### 配置规范

- 所有配置通过 `core.config.settings` 单例访问（`@lru_cache` 保证）
- 新增配置项加到 `Settings` 类并在 `.env.example` 中文档化
- 使用 `AliasChoices` 支持带服务前缀的环境变量名（如 `USER_DATABASE_URL`）
- 生产环境敏感配置（密钥、数据库 URL）必须通过环境变量注入
- 启动时校验 `JWT_SECRET_KEY` 和 `INTERNAL_SECRET` 最小长度（32 字符）

### 错误处理

- 业务异常使用 `common.core.exceptions` 中的层级异常类
- Gateway 错误通过 `BaseGateway._handle_error()` + `error_map` 自动映射
- 禁止裸 `except Exception` 吞掉错误（除非有明确的降级逻辑并记录日志）
- 全局 exception handler 自动返回 `{code, message}` + `X-Request-ID` header

### 认证体系

- JWT access token（短期，默认 15min）+ refresh token（长期，默认 7 天）
- Refresh token 存储为 bcrypt hash，轮换时同时更新 JTI 和 hash
- 内部服务调用使用 HMAC-SHA256 签名（canonical body + path + timestamp + caller）
- 签名 TTL 默认 30s 防重放，可配置 `allowed_callers` 白名单

### 数据库迁移

- 使用 Alembic，迁移文件在 `migrations/versions/`
- 主键使用 Snowflake ID，用户可见标识使用 NanoID UID（10 字符）
- 金额字段使用 `BigInteger` 微分单位（1 CNY = 1,000,000）

## 命令

```bash
# 开发启动
cd services/user-service
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Lint
ruff check src/

# 数据库迁移
cd migrations && alembic upgrade head

# Worker
arq src.core.worker.WorkerSettings
```

## 文件命名

- Controller: `controllers/{domain}.py`
- Service: `services/{domain}_service.py`
- Repository: `repositories/{domain}_repository.py`
- Schema: `schemas/{domain}.py` 或 `schemas/internal_{domain}.py`
- Model: `models/{domain}.py`
- Gateway: `gateways/{target_domain}.py`
