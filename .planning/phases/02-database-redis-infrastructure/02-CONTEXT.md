# Phase 2: Database & Redis Infrastructure - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

api-service 连接合并后的 eucal_ai 数据库和 Redis（3 个逻辑 DB），配置生产安全的连接池参数，实现进程级 Snowflake ID 安全，创建 Alembic baseline 迁移。完成后 lifespan 启动时自动初始化 DB engine、Redis pools、Snowflake generator，/ready 端点验证所有连接健康。

不包含：ORM models 迁移（Phase 3）、业务逻辑、controller 端点。

</domain>

<decisions>
## Implementation Decisions

### Alembic 迁移策略
- **D-01:** 全新 baseline — 生成一个包含所有表当前最终状态的 DDL 迁移作为 api-service 起点
- **D-02:** 旧迁移历史保留在原服务目录（user-service/migrations/, admin-service/migrations/）作为参考，不迁移到新服务
- **D-03:** api-service 的 Alembic 迁移链从 revision 1 开始，无历史依赖

### 连接池配置
- **D-04:** DB 连接池 pool_size=5, max_overflow=10（每 worker 最大 15 连接，4 workers 总计 60，MySQL 151 限制内留有余量）
- **D-05:** pool_pre_ping=True 保持（检测断连）
- **D-06:** pool_recycle=1800（30 分钟回收，避免 MySQL wait_timeout 断连）
- **D-07:** Redis 3 个逻辑 DB 各自独立连接池：db/0 (session/rate-limit), db/1 (ARQ worker queue), db/2 (cache)
- **D-08:** Redis 连接池不设 max_connections 限制（redis-py 默认行为，单实例足够）

### Snowflake ID 多 worker 安全
- **D-09:** 进程级 worker_id — 在 lifespan startup 时为每个 fork 进程分配不同的 instance_id
- **D-10:** 实现方式：利用 uvicorn worker 编号或 os.getpid() 结合 datacenter_id 计算唯一 instance_id，确保 4 个 worker 进程零碰撞
- **D-11:** datacenter_id 保持为 1（单数据中心部署），worker_id 范围 0-3 对应 4 个 workers

### DB 模块架构
- **D-12:** 单一 Base + 单一 ServiceDatabaseRuntime 实例，位于 `api_service/core/db.py`
- **D-13:** Base 使用 Phase 1 已创建的 `api_service/common/infra/db/base.py` 中的 `Base(DeclarativeBase)`
- **D-14:** `get_db` 作为 FastAPI Depends 暴露给 controllers，通过 `from api_service.core.db import get_db`
- **D-15:** 所有 ORM models（Phase 3）继承同一个 Base

### Lifespan 资源注册
- **D-16:** DB engine 注册 priority=20（在 logging=0, snowflake=10 之后）
- **D-17:** Redis pools 注册 priority=30（在 DB 之后，因为某些 Redis 操作可能依赖 DB 状态）
- **D-18:** 所有资源的 shutdown_fn 必须注册，确保优雅关闭

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Migration
- `docs/architecture-refactoring.md` — 完整架构重设计方案，含连接池计算和部署约束
- `docs/architecture-refactoring-detail.md` — 详细实现手册，含 DB 初始化模式

### Existing DB Infrastructure (migration source)
- `services/user-service/src/core/db.py` — 现有 DB 模块模式（Base + Runtime 实例）
- `services/user-service/src/common/db/runtime.py` — ServiceDatabaseRuntime 完整实现
- `services/user-service/src/common/redis.py` — Redis 连接池模式（init/get/close/check_ready）
- `services/user-service/src/common/cache.py` — Cache Redis 独立池 + cache_get_or_fetch helper

### Existing Migrations (baseline source)
- `services/user-service/migrations/versions/` — 13 个迁移，最终表结构参考
- `services/admin-service/migrations/versions/` — 8 个迁移，最终表结构参考
- `services/user-service/migrations/env.py` — Alembic env.py 配置参考

### Snowflake ID
- `services/user-service/src/common/utils/snowflake.py` — 已迁移到 api_service/common/utils/snowflake.py

### Phase 1 产出（已就绪）
- `services/api-service/api_service/common/infra/db/base.py` — Base(DeclarativeBase) + Mixins
- `services/api-service/api_service/common/infra/db/runtime.py` — ServiceDatabaseRuntime
- `services/api-service/api_service/common/infra/redis.py` — init_redis/get_redis/close_redis
- `services/api-service/api_service/common/infra/cache.py` — init_cache_redis/close_cache_redis
- `services/api-service/api_service/common/utils/snowflake.py` — configure_snowflake/generate_snowflake_id
- `services/api-service/api_service/core/lifespan.py` — LifespanRegistry
- `services/api-service/api_service/core/config.py` — ApiServiceSettings (DATABASE_URL, REDIS_URL, etc.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ServiceDatabaseRuntime`: 已迁移到 api_service，可直接实例化使用
- `init_redis` / `init_cache_redis`: 已迁移，接受 URL 参数，返回后可通过 get_redis() 获取
- `LifespanRegistry`: Phase 1 已实现，直接 register() 新资源即可
- `configure_snowflake`: 已迁移，需要扩展支持进程级 worker_id 分配

### Established Patterns
- 资源初始化模式：`init_xxx(url) → get_xxx() → close_xxx()`，全局单例
- DB 依赖注入：`async def get_db() -> AsyncGenerator[AsyncSession, None]`
- 健康检查模式：`check_xxx_ready() -> tuple[bool, str | None]`
- Alembic env.py：使用 `_env_shared.py` 共享配置加载逻辑

### Integration Points
- `api_service/core/lifespan.py` — 注册 DB/Redis/Snowflake 初始化
- `api_service/main.py` — lifespan 已接入，新资源自动随 app 启动
- `api_service/common/health.py` — `build_readiness_response` 需要 DB/Redis 健康检查结果
- `api_service/core/config.py` — DATABASE_URL, REDIS_URL, CACHE_REDIS_URL, WORKER_QUEUE_REDIS_URL 已定义

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches based on existing patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 2-Database & Redis Infrastructure*
*Context gathered: 2026-05-18*
