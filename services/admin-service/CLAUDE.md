# Admin-Service 开发规范

## 项目概述

FastAPI + SQLAlchemy Async + Redis + ARQ Worker 的管理后台微服务。

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
Controllers → Gateways (BaseGateway 子类)
    ↓
common/internal.py (HMAC 签名 + 熔断 + 重试 + 连接池)
```

## 核心规范

### Gateway 层

- 所有 Gateway 必须继承 `common.gateway.base.BaseGateway`
- 在 `__init__` 中声明 `base_url`、`timeout`、`error_map`
- 业务方法直接调用 `self._get()` / `self._post()` / `self._request()`，不要手写 try/except
- Gateway 实例在 controller 中作为**模块级单例**创建，不要在 handler 内 new

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
```

### HTTP Client

- 禁止在业务代码中 `async with httpx.AsyncClient(...) as client:` 创建临时 client
- 使用 `common.internal.get_internal_client(base_url, timeout=...)` 获取共享连接池 client
- 连接池在 `main.py` lifespan shutdown 中通过 `close_internal_clients()` 关闭

### Repository 层

- 继承 `BaseRepository[ModelT]`
- 分页查询优先使用 `self.get_list(ListParams(...), options=[...])` 而非手动 count + offset
- 需要 eager loading 时通过 `options=[selectinload(...)]` 参数传入
- 自定义查询方法仅用于 `get_list` 无法覆盖的复杂场景（JOIN、聚合等）

### Service 层

- 使用 `@staticmethod` + `db: AsyncSession` 作为第一参数
- 审计记录使用 `AdminAuditService.record_auto()`，ip/ua 自动从 request context 获取
- 方法签名中**不要**传递 `ip_address` / `user_agent` 参数
- CPU 密集操作（bcrypt 等）必须使用 `asyncio.to_thread()` 包装的异步版本

### Controller 层

- 保持薄层，只做参数提取、调用 service、构造 response
- 鉴权通过 `Depends(require_active_admin)` 或 `Depends(require_super_admin)`
- 不要在 controller 中调用 `get_request_meta()`（已由 middleware 自动设置 context）

### 异步规范

- 所有 handler 和 service 方法都是 `async`
- 禁止在 async 上下文中调用阻塞函数（bcrypt、文件 IO、同步 HTTP）
- 阻塞操作使用 `await asyncio.to_thread(blocking_fn, ...)`
- 并发 IO 使用 `asyncio.gather()` + `asyncio.Semaphore` 限流

### 日志规范

- 模块级 logger：`logger = logging.getLogger(__name__)`
- 结构化日志使用 `log_event(logger, level, "eventName", key=value)`
- 禁止内联 `logging.getLogger("xxx").info(...)` 
- 敏感信息（API key、密码）不得出现在日志中，observability 层已有自动脱敏

### 配置规范

- 所有配置通过 `core.config.settings` 单例访问
- 新增配置项加到 `Settings` 类并在 `.env.example` 中文档化
- 使用 `AliasChoices` 支持带服务前缀的环境变量名
- 生产环境敏感配置（密钥、数据库 URL）必须通过环境变量注入

### 错误处理

- 业务异常使用 `common.core.exceptions` 中的层级异常类
- Gateway 错误通过 `BaseGateway._handle_error()` + `error_map` 自动映射
- 禁止裸 `except Exception` 吞掉错误（除非有明确的降级逻辑并记录日志）

### 数据库迁移

- 使用 Alembic，迁移文件命名：`YYYYMMDD_description.py`
- 启动时自动校验 schema 版本（`ensure_database_at_head`）
- 主键使用 Snowflake ID，用户可见标识使用 NanoID UID

## 命令

```bash
# 开发启动
cd services/admin-service
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

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
- Schema: `schemas/{domain}.py`
- Model: `models/{domain}.py`
- Gateway: `gateways/{target_domain}.py`
