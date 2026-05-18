# Phase 1 Research: Project Scaffold & Common Layer

**Researched:** 2026-05-18
**Requirements:** INFRA-01, INFRA-07, INFRA-08, INFRA-09
**Confidence:** HIGH (all source code directly analyzed)

---

## Summary of Findings

1. **Common 层高度一致**：user-service 和 admin-service 的 common/ 有 90% 重叠，admin 仅多出 3 个文件（token_blacklist.py, request_context.py, utils/crypto.py）和 1 个 DB 模块（schema_version.py）
2. **Settings 合并清晰**：三个服务的 Settings 类都继承同一个 BaseServiceSettings，合并只需取并集字段
3. **Lifespan 模式成熟**：user-service 的 lifespan 已是标准模式，可直接扩展为 LifespanRegistry
4. **Phase 1 依赖精简**：scaffold 阶段只需 FastAPI + Pydantic + Redis + 基础工具，不需要 DB/LLM SDK
5. **Import 路径变更**：从 `src/common/...` 变为 `api_service/common/...`（D-08 决策）
6. **Reference project (new-api)** 验证了按职责域分组 common 层的合理性

---

## 1. Existing Common Layer Analysis

### 1.1 User-Service Common (Base — 最完整)

```
common/
├── __init__.py
├── config.py              # BaseServiceSettings (所有服务的基类)
├── cache.py               # Redis db/2 缓存池 + cache_get_or_fetch helper
├── health.py              # check_database_ready + build_readiness_response
├── internal.py            # HMAC 签名验证 + httpx 连接池 + 熔断器 + 重试
├── internal_logs.py       # Ring buffer 日志读取端点
├── observability.py       # 结构化 JSON 日志 + request-id middleware
├── redis.py               # Redis db/0 主连接池
├── api/
│   └── pagination.py      # 分页工具
├── core/
│   ├── exceptions.py      # 异常层级 (APIException → 子类)
│   └── exception_handlers.py  # 全局异常处理器
├── db/
│   ├── base.py            # TimestampMixin, SnowflakeIdMixin, SoftDeleteMixin
│   ├── runtime.py         # ServiceDatabaseRuntime (engine/session lifecycle)
│   ├── repository.py      # BaseRepository[T]
│   ├── query.py           # 查询工具
│   └── _env_shared.py     # Alembic env 共享
├── gateway/
│   └── base.py            # BaseGateway (HTTP 代理基类)
└── utils/
    ├── jwt.py             # JWT encode/decode
    ├── nanoid_uid.py      # NanoID 生成
    ├── password.py        # bcrypt hash (async wrapper)
    ├── snowflake.py       # Snowflake ID 配置
    └── timezone.py        # 时区工具
```

### 1.2 Admin-Service Unique Modules (需额外迁移)

| 文件 | 功能 | 迁移目标 |
|------|------|---------|
| `common/token_blacklist.py` | Redis-backed JWT 黑名单 (admin token 注销) | `api_service/common/token_blacklist.py` |
| `common/request_context.py` | ContextVar: IP/UA 审计上下文 | `api_service/common/request_context.py` |
| `common/utils/crypto.py` | AES-256-GCM 加解密 (pool account 密钥) | `api_service/common/utils/crypto.py` |
| `common/db/schema_version.py` | Alembic 版本校验 (ensure_database_at_head) | `api_service/common/db/schema_version.py` |

### 1.3 Router-Service Common (最小集)

Router-service 的 common/ 只有 4 个文件：`config.py`, `internal.py`, `internal_logs.py`, `observability.py`。全部是 user-service 的子集，无独有模块。

### 1.4 Overlap Matrix

| Module | user-service | admin-service | router-service |
|--------|:---:|:---:|:---:|
| config.py (BaseServiceSettings) | ✅ | ✅ (identical) | ✅ (identical) |
| observability.py | ✅ | ✅ (identical) | ✅ (identical) |
| internal.py | ✅ | ✅ (identical) | ✅ (identical) |
| internal_logs.py | ✅ | ✅ (identical) | ✅ (identical) |
| redis.py | ✅ | ✅ (identical) | — |
| cache.py | ✅ | — | — |
| health.py | ✅ | ✅ (identical) | — |
| api/pagination.py | ✅ | ✅ (identical) | — |
| core/exceptions.py | ✅ | ✅ (identical) | — |
| core/exception_handlers.py | ✅ | ✅ (identical) | — |
| db/* | ✅ | ✅ (identical) | — |
| gateway/base.py | ✅ | ✅ (identical) | — |
| utils/* | ✅ | ✅ + crypto.py | — |
| token_blacklist.py | — | ✅ | — |
| request_context.py | — | ✅ | — |
| db/schema_version.py | — | ✅ | — |

---

## 2. Reference Project Analysis (new-api-main)

### 2.1 Directory Structure Pattern

```
new-api-main/
├── common/           # 基础设施工具 (crypto, database, email, redis, limiter, utils)
├── constant/         # 全局常量
├── controller/       # HTTP 控制器 (平铺，按域命名)
├── dto/              # 数据传输对象
├── middleware/       # HTTP 中间件
├── model/            # ORM 模型
├── pkg/              # 可复用包 (billingexpr, cachex, ionet)
├── relay/            # LLM 转发核心 (channel, common, helper, adapters)
├── router/           # 路由注册 (api-router, relay-router, dashboard)
├── service/          # 业务逻辑
├── setting/          # 配置 (按域分子目录: billing, model, operation, performance, system)
└── types/            # 类型定义
```

### 2.2 Key Patterns Adopted

1. **Common 层平铺 + 子目录**：new-api 的 `common/` 是平铺文件 + `limiter/` 子目录。我们的决策 D-02 采用类似模式但更结构化（按职责域分子目录）。

2. **Setting 按域分组**：new-api 的 `setting/` 有 `billing_setting/`, `model_setting/`, `operation_setting/` 等子目录。我们的决策 D-06 选择单一 Settings 类 + 注释分区（更适合 pydantic-settings 的 env 加载模式）。

3. **Router 集中注册**：new-api 的 `router/main.go` 调用 `SetApiRouter()`, `SetRelayRouter()`, `SetDashboardRouter()` 分别注册。我们的 `core/router.py` 将采用相同模式。

4. **Relay 独立子目录**：new-api 将 relay 逻辑放在顶级 `relay/` 目录。我们的决策 D-11 将 relay 放在 `services/relay/` 子目录下。

5. **Health Check**：new-api 的 `controller/misc.go` 包含 `/api/status` 端点。我们的 `/health` + `/ready` 双端点模式更符合 K8s 标准。

---

## 3. File Migration Plan for Phase 1

### 3.1 Phase 1 Scope (Only Common Layer + Scaffold)

根据决策 D-14（渐进式策略），Phase 1 只创建骨架和 common 层，不包含 models/repositories/services/controllers。

### 3.2 Target Directory Structure

```
services/api-service/
├── api_service/                    # 源码根 (D-08)
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口 + lifespan
│   ├── common/                    # 合并后的公共层
│   │   ├── __init__.py
│   │   ├── config.py             # BaseServiceSettings (不变)
│   │   ├── cache.py              # Redis db/2 缓存池
│   │   ├── health.py             # 健康检查工具
│   │   ├── internal.py           # HMAC 签名验证 + httpx 连接池
│   │   ├── internal_logs.py      # Ring buffer 日志端点
│   │   ├── observability.py      # 结构化日志 + middleware
│   │   ├── redis.py              # Redis db/0 主连接池
│   │   ├── request_context.py    # ContextVar (IP/UA)
│   │   ├── token_blacklist.py    # JWT 黑名单
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── pagination.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── exceptions.py
│   │   │   └── exception_handlers.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # Mixins
│   │   │   ├── runtime.py        # ServiceDatabaseRuntime
│   │   │   ├── repository.py     # BaseRepository[T]
│   │   │   ├── query.py
│   │   │   ├── schema_version.py # Alembic 版本校验
│   │   │   └── _env_shared.py
│   │   ├── gateway/
│   │   │   ├── __init__.py
│   │   │   └── base.py           # BaseGateway (仅供 inference_client)
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── jwt.py
│   │       ├── nanoid_uid.py
│   │       ├── password.py
│   │       ├── snowflake.py
│   │       ├── timezone.py
│   │       └── crypto.py         # AES-256-GCM
│   ├── core/                      # 应用核心配置
│   │   ├── __init__.py
│   │   ├── config.py             # ApiServiceSettings
│   │   ├── database.py           # DB engine 代理
│   │   ├── lifespan.py           # LifespanRegistry
│   │   └── router.py             # 路由注册 (空占位)
│   ├── controllers/               # 空占位
│   │   └── __init__.py
│   ├── services/                  # 空占位
│   │   └── __init__.py
│   ├── models/                    # 空占位
│   │   └── __init__.py
│   ├── repositories/              # 空占位
│   │   └── __init__.py
│   └── schemas/                   # 空占位
│       └── __init__.py
├── migrations/                    # Alembic (Phase 2 填充)
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   └── test_health.py
├── pyproject.toml
├── .env.example
└── CLAUDE.md
```

### 3.3 Concrete File Migration Mapping (Phase 1)

| Source | Target | Action |
|--------|--------|--------|
| `user-service/src/common/__init__.py` | `api_service/common/__init__.py` | Copy |
| `user-service/src/common/config.py` | `api_service/common/config.py` | Copy |
| `user-service/src/common/cache.py` | `api_service/common/cache.py` | Copy |
| `user-service/src/common/health.py` | `api_service/common/health.py` | Copy |
| `user-service/src/common/internal.py` | `api_service/common/internal.py` | Copy |
| `user-service/src/common/internal_logs.py` | `api_service/common/internal_logs.py` | Copy |
| `user-service/src/common/observability.py` | `api_service/common/observability.py` | Copy |
| `user-service/src/common/redis.py` | `api_service/common/redis.py` | Copy |
| `admin-service/src/common/request_context.py` | `api_service/common/request_context.py` | Copy |
| `admin-service/src/common/token_blacklist.py` | `api_service/common/token_blacklist.py` | Copy |
| `user-service/src/common/api/pagination.py` | `api_service/common/api/pagination.py` | Copy |
| `user-service/src/common/core/exceptions.py` | `api_service/common/core/exceptions.py` | Copy |
| `user-service/src/common/core/exception_handlers.py` | `api_service/common/core/exception_handlers.py` | Copy |
| `user-service/src/common/db/base.py` | `api_service/common/db/base.py` | Copy |
| `user-service/src/common/db/runtime.py` | `api_service/common/db/runtime.py` | Copy |
| `user-service/src/common/db/repository.py` | `api_service/common/db/repository.py` | Copy |
| `user-service/src/common/db/query.py` | `api_service/common/db/query.py` | Copy |
| `user-service/src/common/db/_env_shared.py` | `api_service/common/db/_env_shared.py` | Copy |
| `admin-service/src/common/db/schema_version.py` | `api_service/common/db/schema_version.py` | **Modify** (update service configs) |
| `user-service/src/common/gateway/base.py` | `api_service/common/gateway/base.py` | Copy |
| `user-service/src/common/utils/jwt.py` | `api_service/common/utils/jwt.py` | Copy |
| `user-service/src/common/utils/nanoid_uid.py` | `api_service/common/utils/nanoid_uid.py` | Copy |
| `user-service/src/common/utils/password.py` | `api_service/common/utils/password.py` | Copy |
| `user-service/src/common/utils/snowflake.py` | `api_service/common/utils/snowflake.py` | Copy |
| `user-service/src/common/utils/timezone.py` | `api_service/common/utils/timezone.py` | Copy |
| `admin-service/src/common/utils/crypto.py` | `api_service/common/utils/crypto.py` | Copy |
| — | `api_service/core/config.py` | **New** (merge 3 service settings) |
| — | `api_service/core/database.py` | **New** (single engine proxy) |
| — | `api_service/core/lifespan.py` | **New** (LifespanRegistry) |
| — | `api_service/core/router.py` | **New** (empty placeholder) |
| — | `api_service/main.py` | **New** (FastAPI app + lifespan) |

---

## 4. Phase 1 Dependencies (pyproject.toml)

根据决策 D-18，合并三服务依赖，去掉 litellm。Phase 1 scaffold 需要完整依赖列表（即使 DB/Redis 在 Phase 2 才真正使用，pyproject.toml 应一次性定义好）。

```toml
[project]
name = "eucal-ai-api-service"
version = "1.0.0"
description = "EucalAI unified API service: user + admin + relay"
requires-python = ">=3.10"
dependencies = [
    # Web framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-multipart>=0.0.6",
    "email-validator>=2.1.0",
    # HTTP client (internal calls to inference-service)
    "httpx>=0.26.0",
    # Rate limiting
    "slowapi>=0.1.9",
    # Database
    "sqlalchemy[asyncio]>=2.0.25",
    "aiomysql>=0.2.0",
    "alembic>=1.14.0",
    # Auth & Security
    "python-jose[cryptography]>=3.3.1",
    "passlib[bcrypt]>=1.7.4",
    "bcrypt>=3.2.0,<4.0.0",
    "cryptography>=42.0.0",
    # ID generation
    "snowflake-id>=1.0.0",
    "nanoid>=2.0.0",
    # Redis
    "redis>=5.0",
    # Background jobs
    "arq>=0.26.0",
    # LLM SDKs (relay upstream calls)
    "openai>=1.40.0",
    "anthropic>=0.34.0",
    # Utilities
    "cachetools>=5.0.0",
    "python-dotenv>=1.0.0",
    "tzdata>=2025.3",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx",  # TestClient
    "coverage>=7.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["api_service"]

[[tool.uv.index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true

[tool.ruff]
target-version = "py310"
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### Key Differences from Existing Services

| Change | Reason |
|--------|--------|
| Removed `litellm>=1.0.0` | D-18: 50MB+ 依赖，直接用 openai + anthropic SDK |
| Added `openai>=1.40.0` | From router-service (relay upstream) |
| Added `anthropic>=0.34.0` | From router-service (relay upstream) |
| Added `cryptography>=42.0.0` | From admin-service (AES-256-GCM) |
| Bumped FastAPI to `>=0.115.0` | Pydantic v2 native, improved DI perf |
| Bumped uvicorn to `>=0.34.0` | HTTP/2, improved shutdown |
| Package root: `api_service` | D-08: 单一包，非 src/ 多包 |

---

## 5. LifespanRegistry Pattern

### 5.1 Design (Based on D-15, D-16)

```python
"""api_service/core/lifespan.py — Resource lifecycle registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class _Resource:
    name: str
    init_fn: Callable[[], Awaitable[None]]
    shutdown_fn: Callable[[], Awaitable[None]] | None
    priority: int  # lower = earlier init, later shutdown


@dataclass
class LifespanRegistry:
    """Register resources with init/shutdown functions, execute in priority order."""

    _resources: list[_Resource] = field(default_factory=list)
    _initialized: list[str] = field(default_factory=list)

    def register(
        self,
        name: str,
        init_fn: Callable[[], Awaitable[None]],
        shutdown_fn: Callable[[], Awaitable[None]] | None = None,
        priority: int = 100,
    ) -> None:
        self._resources.append(_Resource(name=name, init_fn=init_fn, shutdown_fn=shutdown_fn, priority=priority))

    async def startup(self) -> None:
        """Initialize all resources in priority order. Fail-fast on error."""
        sorted_resources = sorted(self._resources, key=lambda r: r.priority)
        for resource in sorted_resources:
            try:
                await resource.init_fn()
                self._initialized.append(resource.name)
                logger.info("resource_initialized", extra={"resource": resource.name})
            except Exception:
                logger.critical("resource_init_failed", extra={"resource": resource.name}, exc_info=True)
                # Clean up already-initialized resources (reverse order)
                await self._cleanup()
                raise

    async def shutdown(self) -> None:
        """Shutdown all initialized resources in reverse priority order."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        sorted_resources = sorted(self._resources, key=lambda r: r.priority, reverse=True)
        for resource in sorted_resources:
            if resource.name in self._initialized and resource.shutdown_fn:
                try:
                    await resource.shutdown_fn()
                    logger.info("resource_shutdown", extra={"resource": resource.name})
                except Exception:
                    logger.warning("resource_shutdown_failed", extra={"resource": resource.name}, exc_info=True)
        self._initialized.clear()
```

### 5.2 Usage in main.py

```python
from contextlib import asynccontextmanager
from api_service.core.lifespan import LifespanRegistry

registry = LifespanRegistry()

# Phase 1: Basic resources
registry.register("logging", init_fn=_init_logging, priority=0)
registry.register("snowflake", init_fn=_init_snowflake, priority=10)

# Phase 2 will add:
# registry.register("redis", init_fn=_init_redis, shutdown_fn=close_redis, priority=20)
# registry.register("cache_redis", init_fn=_init_cache_redis, shutdown_fn=close_cache_redis, priority=21)
# registry.register("database", init_fn=_init_database, shutdown_fn=close_db, priority=30)
# registry.register("schema_check", init_fn=_check_schema, priority=40)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.startup()
    yield
    await registry.shutdown()
```

### 5.3 Phase 1 Lifespan (Minimal)

Phase 1 的 lifespan 只初始化：
1. **Logging** (priority=0) — `configure_logging_from_settings(settings)`
2. **Snowflake** (priority=10) — `configure_snowflake(worker_id=settings.SNOWFLAKE_WORKER_ID)`

`/health` 返回静态 JSON，`/ready` 在 Phase 1 也返回静态 OK（Phase 2 加入 DB/Redis 检查）。

### 5.4 Priority Allocation Plan

| Priority | Resource | Phase |
|----------|----------|-------|
| 0 | Logging | 1 |
| 10 | Snowflake ID | 1 |
| 20 | Redis (main) | 2 |
| 21 | Redis (cache) | 2 |
| 30 | Database engine + session factory | 2 |
| 40 | Schema version check | 2 |
| 50 | Bootstrap superadmin | 2 |
| 60 | Internal HTTP clients | 3 |
| 70 | Relay components (inference_client, channel_selector, sdk_pool, rate_limiter) | 3 |

---

## 6. Potential Conflicts and Issues

### 6.1 Import Path Changes

**Critical change:** 现有服务使用 `from common.xxx import ...`（相对于 `src/`），新服务使用 `from api_service.common.xxx import ...`（绝对包路径）。

| Old Pattern | New Pattern |
|-------------|-------------|
| `from common.config import BaseServiceSettings` | `from api_service.common.config import BaseServiceSettings` |
| `from common.observability import log_event` | `from api_service.common.observability import log_event` |
| `from common.db.runtime import ServiceDatabaseRuntime` | `from api_service.common.db.runtime import ServiceDatabaseRuntime` |
| `from core.config import settings` | `from api_service.core.config import settings` |

**Migration strategy:** 复制文件后，用 `ruff` 或 `sed` 批量替换 import 前缀。common 层内部的相对 import（如 `from common.redis import get_redis`）需要改为 `from api_service.common.redis import get_redis`。

### 6.2 schema_version.py Modification Required

现有 `schema_version.py` 硬编码了两个服务的配置：
```python
for service_name, package, db_env in [
    ("admin-service", "models", "ADMIN_DATABASE_URL"),
    ("user-service", "user_service", "USER_DATABASE_URL"),
]:
```

合并后需要改为单一服务配置：
```python
for service_name, package, db_env in [
    ("api-service", "api_service", "DATABASE_URL"),
]:
```

### 6.3 ServiceDatabaseRuntime Constructor

现有 `ServiceDatabaseRuntime.__init__` 接受 `base: type[DeclarativeBase]` 参数，但 `user-service/src/core/db.py` 实际使用时传入了 Base。合并后 `core/database.py` 需要 import 正确的 Base：

```python
from api_service.common.db.base import TimestampMixin  # Base 在哪里定义？
```

**Issue:** 现有代码中 `common/db/base.py` 只定义了 Mixins，实际的 `DeclarativeBase` 在各服务的 `models/__init__.py` 中定义。Phase 1 需要在 `common/db/base.py` 中添加一个共享的 `Base` 类：

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### 6.4 BaseServiceSettings Validation

`BaseServiceSettings.validate_required_fields` 要求 `JWT_SECRET_KEY` 和 `INTERNAL_SECRET` 非空。Phase 1 开发时需要 `.env` 文件提供这些值，否则 Settings 实例化会失败。

**Solution:** `.env.example` 必须包含示例值，开发者 copy 后即可启动。

### 6.5 No Naming Conflicts in Common Layer

经过逐文件对比，admin-service 和 user-service 的 common 层没有同名但不同实现的文件。所有重叠文件内容完全一致（同一份代码复制到两个服务）。唯一需要"合并"的是 `core/exceptions.py`，但实际上 admin-service 的异常类是 user-service 的子集，直接使用 user-service 版本即可。

---

## 7. ApiServiceSettings Design

### 7.1 Merged Configuration (Based on D-06, D-07)

```python
"""api_service/core/config.py"""

from functools import lru_cache
from typing import List, Optional, Union

from pydantic import Field

from api_service.common.config import BaseServiceSettings


class ApiServiceSettings(BaseServiceSettings):
    """Unified settings for api-service (merged admin + user + router)."""

    PROJECT_NAME: str = "Eucal AI API Service"
    SERVICE_NAME: str = "api-service"
    DESCRIPTION: str = "Eucal AI Unified API Service"
    PORT: int = 8000

    # --- Database ---
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/eucal_ai"

    # --- Redis ---
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    CACHE_REDIS_URL: str = "redis://127.0.0.1:6379/2"
    WORKER_QUEUE_REDIS_URL: str = "redis://127.0.0.1:6379/1"

    # --- Inference (唯一远程依赖) ---
    INFERENCE_SERVICE_URL: str = "http://127.0.0.1:8004"
    INFERENCE_SERVICE_SECRET: str = ""

    # --- Admin ---
    BOOTSTRAP_SUPERADMIN_ENABLED: bool = False
    BOOTSTRAP_SUPERADMIN_EMAIL: Optional[str] = None
    BOOTSTRAP_SUPERADMIN_PASSWORD: Optional[str] = None
    BOOTSTRAP_SUPERADMIN_NAME: Optional[str] = None
    PROVIDER_SECRET_MASTER_KEY: str = ""
    ADMIN_TOKEN_EXPIRE_MINUTES: int = 480

    # --- User ---
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_FROM: str = "Eucal AI"
    MAX_API_KEYS_PER_USER: int = 20
    LOGIN_MAX_FAILURES: int = 5
    EMAIL_CODE_EXPIRE_MINUTES: int = 5

    # --- Relay ---
    CHANNEL_MAX_RETRIES: int = 2
    CHANNEL_COOLDOWN_SECONDS: float = 30.0
    CHANNEL_AUTO_DISABLE_ENABLED: bool = True
    CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD: int = 5
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_USER_RPM: int = 20
    RATE_LIMIT_GLOBAL_RPM: int = 0
    SDK_CLIENT_POOL_MAX_SIZE: int = 64
    ANTHROPIC_NATIVE_SLUGS: list = ["anthropic"]
    CHANNEL_AFFINITY_ENABLED: bool = False
    CHANNEL_AFFINITY_TTL: int = 3600

    # --- CORS ---
    ALLOWED_HOSTS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # --- Logging ---
    LOG_FILE_PREFIX: str = "api"

    # --- Snowflake ---
    SNOWFLAKE_WORKER_ID: int = 1


@lru_cache
def get_settings() -> ApiServiceSettings:
    return ApiServiceSettings()

settings = get_settings()
```

### 7.2 Removed Configuration Items

| Removed | Reason |
|---------|--------|
| `USER_SERVICE_URL` | No longer needed (in-process) |
| `ADMIN_SERVICE_URL` | No longer needed (in-process) |
| `ROUTER_SERVICE_URL` | No longer needed (in-process) |
| `CONFIG_REFRESH_INTERVAL_SECONDS` | No HTTP polling (direct DB) |
| `CALLLOG_FLUSH_INTERVAL` | No buffer (direct DB write) |
| `CALLLOG_MAX_BUFFER` | No buffer |
| `AliasChoices` on DATABASE_URL | D-07: no service prefix |

### 7.3 Validation Changes

- `PROVIDER_SECRET_MASTER_KEY` validation deferred: Phase 1 不需要加密功能，可以为空。在 Phase 2 迁移 admin 逻辑时再加 validator。
- `JWT_SECRET_KEY` + `INTERNAL_SECRET` validation 保持不变（来自 BaseServiceSettings）。

---

## 8. Existing Code Patterns to Preserve

### 8.1 Logging Pattern

```python
import logging
from api_service.common.observability import log_event

logger = logging.getLogger(__name__)

# Usage
log_event(logger, logging.INFO, "service_started", service="api-service")
```

### 8.2 Settings Singleton Pattern

```python
from functools import lru_cache

@lru_cache
def get_settings() -> ApiServiceSettings:
    return ApiServiceSettings()

settings = get_settings()
```

### 8.3 Health Check Pattern

```python
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}

@app.get("/ready", tags=["health"])
async def readiness_check():
    # Phase 1: static OK
    return {"status": "ready", "service": settings.SERVICE_NAME}
    # Phase 2: add DB/Redis checks via build_readiness_response()
```

### 8.4 Middleware Order (D-14 from PITFALLS)

```python
# FastAPI middleware executes in REVERSE order of add_middleware() calls
# So add in this order: last added = first executed
app.add_middleware(CORSMiddleware, ...)  # 3rd added = 1st executed
install_observability(app, ...)          # 2nd added (via middleware decorator)
# request_context middleware             # 1st added = last executed
```

### 8.5 Exception Handler Registration

```python
from api_service.common.core.exception_handlers import register_exception_handlers
register_exception_handlers(app)
```

---

## 9. Verification Criteria (INFRA-01, INFRA-07, INFRA-08, INFRA-09)

| Requirement | Verification |
|-------------|-------------|
| INFRA-01: api-service 可启动并通过 /health 和 /ready | `uvicorn api_service.main:app --port 8000` + `curl /health` → 200 + `curl /ready` → 200 |
| INFRA-07: common 层合并 | 所有 26 个 common 文件存在且 import 无错误 (`ruff check api_service/`) |
| INFRA-08: 统一 Settings 配置类 | `ApiServiceSettings` 包含所有三服务配置项，`settings` 单例可实例化 |
| INFRA-09: lifespan 正确管理资源 | LifespanRegistry 存在，Phase 1 注册 logging + snowflake，启动/关闭无报错 |

---

## RESEARCH COMPLETE
