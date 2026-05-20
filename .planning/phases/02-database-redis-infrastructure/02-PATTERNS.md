# Phase 2: Database & Redis Infrastructure - Pattern Map

## Files Overview

| File | Role | Analog | Status |
|------|------|--------|--------|
| `services/api-service/api_service/core/db.py` | infrastructure | `services/user-service/src/core/db.py` | create |
| `services/api-service/api_service/main.py` | integration | `services/api-service/api_service/main.py` (self) | modify |
| `services/api-service/api_service/core/config.py` | config | `services/api-service/api_service/core/config.py` (self) | modify |
| `services/api-service/migrations/alembic.ini` | config | `services/user-service/migrations/alembic.ini` | create |
| `services/api-service/migrations/env.py` | config | `services/user-service/migrations/env.py` | create |
| `services/api-service/migrations/script.py.mako` | config | `services/admin-service/migrations/script.py.mako` | create |
| `services/api-service/migrations/versions/__init__.py` | config | `services/user-service/migrations/versions/__init__.py` | create |
| `services/api-service/migrations/versions/20260519_baseline.py` | migration | `services/admin-service/migrations/versions/20260501_baseline.py` | create |

## Detailed Patterns

### `services/api-service/api_service/core/db.py`

**Role:** infrastructure — ServiceDatabaseRuntime 实例化 + 便捷函数导出
**Analog:** `services/user-service/src/core/db.py`
**Status:** create

**Pattern from analog:**
```python
"""User-service database runtime."""

from sqlalchemy.orm import declarative_base

from common.db.runtime import ServiceDatabaseRuntime

Base = declarative_base()
_runtime = ServiceDatabaseRuntime(Base)

create_engine = _runtime.create_engine
get_engine = _runtime.get_engine
init_session_factory = _runtime.init_session_factory
get_db = _runtime.get_db
get_db_context = _runtime.get_db_context
close_db = _runtime.close_db

__all__ = [
    "Base",
    "close_db",
    "create_engine",
    "get_db",
    "get_db_context",
    "get_engine",
    "init_session_factory",
]
```

**Differences needed:**
- Import path 改为 `from api_service.common.infra.db.runtime import ServiceDatabaseRuntime`
- 不使用 `declarative_base()`，改为导入 Phase 1 已创建的 `from api_service.common.infra.db.base import Base`（D-13）
- 不需要重新定义 Base，直接使用已有的 Base
- 模块 docstring 改为 api-service 相关描述

---

### `services/api-service/api_service/main.py`

**Role:** integration — 注册 DB/Redis lifespan 资源 + 替换 /ready 端点
**Analog:** 自身当前状态（Phase 1 产出）
**Status:** modify

**Pattern from analog (当前 lifespan 注册):**
```python
registry = LifespanRegistry()

async def _init_logging() -> None:
    configure_logging_from_settings(settings)

async def _init_snowflake() -> None:
    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )

registry.register("logging", init_fn=_init_logging, priority=0)
registry.register("snowflake", init_fn=_init_snowflake, priority=10)
```

**Pattern from analog (当前 /ready 占位):**
```python
@app.get("/ready")
async def ready():
    return {
        "status": "ready",
        "service": settings.SERVICE_NAME,
    }
```

**Differences needed:**
- `_init_snowflake` 改为使用 `os.getpid() % 32` 动态计算 worker_id（D-09/D-10/D-11）
- 新增 `_init_database` / `_shutdown_database`（priority=20, D-16）
- 新增 `_init_redis` / `_shutdown_redis`（priority=30, D-17）
- 新增 `_init_cache_redis` / `_shutdown_cache_redis`（priority=30, D-17）
- `/ready` 端点替换为调用 `build_readiness_response` + 组合 DB/Redis 健康检查

---

### `services/api-service/api_service/core/config.py`

**Role:** config — 覆盖连接池默认值
**Analog:** 自身当前状态 + `services/api-service/api_service/common/config.py`（BaseServiceSettings）
**Status:** modify

**Pattern from analog (BaseServiceSettings 默认值):**
```python
DATABASE_POOL_SIZE: int = 10
DATABASE_MAX_OVERFLOW: int = 20
DATABASE_POOL_RECYCLE: int = 1800
DATABASE_POOL_TIMEOUT: int = 10
DATABASE_ECHO: bool = False
```

**Pattern from analog (ApiServiceSettings 当前):**
```python
class ApiServiceSettings(BaseServiceSettings):
    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/eucal_ai"
```

**Differences needed:**
- 在 `ApiServiceSettings` 中覆盖 `DATABASE_POOL_SIZE: int = 5`（D-04）
- 在 `ApiServiceSettings` 中覆盖 `DATABASE_MAX_OVERFLOW: int = 10`（D-04）
- 这些值覆盖 BaseServiceSettings 的 10/20 默认值，适配 2h4g 服务器约束

---

### `services/api-service/migrations/alembic.ini`

**Role:** config — Alembic 配置文件
**Analog:** `services/user-service/migrations/alembic.ini`
**Status:** create

**Pattern from analog:**
```ini
[alembic]
script_location = %(here)s
prepend_sys_path =
service_name = user-service
service_package =
database_env = USER_DATABASE_URL
sqlalchemy.url =

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers = console
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

**Differences needed:**
- `service_name = api-service`
- `service_package = api_service`（注意：user-service 和 admin-service 的 service_package 为空，因为它们的 `_env_shared.py` 走 else 分支 `importlib.import_module("core.db")`）
- `database_env = DATABASE_URL`（合并后统一使用 DATABASE_URL）
- 需要确认 `_load_metadata` 能正确处理 `api_service.db` 路径（可能需要创建 `api_service/db.py` 代理或设 service_package 为空并调整 sys.path）

---

### `services/api-service/migrations/env.py`

**Role:** config — Alembic env.py 代理
**Analog:** `services/user-service/migrations/env.py`
**Status:** create

**Pattern from analog:**
```python
"""Proxy env.py for user-service migrations."""

from common.db._env_shared import run_env

run_env()
```

**Differences needed:**
- Import path 改为 `from api_service.common.infra.db._env_shared import run_env`
- 注意：`_env_shared.py` 的 `_load_metadata` 逻辑会尝试 `importlib.import_module(f"{service_package}.db")`
- 如果 `service_package = "api_service"`，则会尝试 `import api_service.db`，但实际 db 模块在 `api_service.core.db`
- 解决方案选项：
  1. 创建 `api_service/db.py` 作为代理（`from api_service.core.db import Base`）
  2. 设 `service_package` 为空，在 env.py 中手动设置 sys.path
  3. 修改 `_env_shared.py` 支持自定义 db_module 路径
- 推荐方案 1：最小改动，创建 `api_service/db.py` 代理模块

---

### `services/api-service/migrations/script.py.mako`

**Role:** config — Alembic 迁移模板
**Analog:** `services/admin-service/migrations/script.py.mako`
**Status:** create

**Pattern from analog:**
```mako
"""${message}"""

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

**Differences needed:**
- 无差异，直接复制

---

### `services/api-service/migrations/versions/__init__.py`

**Role:** config — Python 包标记
**Analog:** `services/user-service/migrations/versions/__init__.py`
**Status:** create

**Pattern from analog:**
- 空文件

**Differences needed:**
- 无差异

---

### `services/api-service/migrations/versions/20260519_baseline.py`

**Role:** migration — 合并后全量 DDL baseline
**Analog:** `services/admin-service/migrations/versions/20260501_baseline.py` + `services/user-service/migrations/versions/20260423_01_user_baseline.py`
**Status:** create

**Pattern from analog (admin-service baseline 结构):**
```python
"""Admin service consolidated baseline — all tables + seed catalog data."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260501_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `admin_users` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            ...
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_admin_users_uid` (`uid`),
            ...
            CONSTRAINT `fk_admin_users_created_by`
                FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Admin users'
        """
    )
    # ... more tables ...


def downgrade() -> None:
    # DROP TABLE 按依赖逆序
    ...
```

**Pattern from analog (user-service baseline 结构):**
```python
"""User service baseline — all tables with full indexes and constraints."""

from __future__ import annotations

from alembic import op

revision = "20260423_01_user_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `users` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            ...
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Users'
        """
    )
    # ... more tables ...
```

**Differences needed:**
- revision 改为 `"20260519_baseline"`
- 合并两个服务的所有表（约 22 张）到一个 upgrade() 中
- 必须反映所有后续迁移的最终状态（列重命名、CHECK 约束、新增列等）
- 包含 seed data（model_vendors, model_categories, audit_action_definitions 等）
- downgrade() 按 FK 依赖逆序 DROP TABLE
- 金额字段使用 BIGINT 微元（后续迁移 20260430_02_monetary_precision 的最终状态）
- 包含 user-service 的 20260518 迁移变更（refactor_call_logs, record_ip_log）

---

## 补充文件（_env_shared.py 兼容性）

### `services/api-service/api_service/db.py`（代理模块）

**Role:** compatibility — 为 `_env_shared.py` 的 `_load_metadata` 提供入口
**Analog:** 无直接类比（user-service/admin-service 的 `_env_shared.py` 走 else 分支）
**Status:** create

**Pattern from `_env_shared.py` 的 `_load_metadata`:**
```python
def _load_metadata(service_package: str):
    if service_package:
        db_module = importlib.import_module(f"{service_package}.db")
        importlib.import_module(f"{service_package}.models")
    else:
        db_module = importlib.import_module("core.db")
        importlib.import_module("models")
    return db_module.Base.metadata
```

**需要创建的代理:**
```python
"""Proxy module for Alembic _env_shared.py compatibility.

_env_shared._load_metadata imports '{service_package}.db' — this module
re-exports Base from the actual location at api_service.core.db.
"""
from api_service.core.db import Base

__all__ = ["Base"]
```

**Differences needed:**
- 这是一个纯代理模块，仅为满足 `_load_metadata` 的 import 路径约定
- 同时需要 `api_service/models/__init__.py`（Phase 3 创建 ORM models 时使用，Phase 2 可创建空文件占位）

---

## PATTERN MAPPING COMPLETE
