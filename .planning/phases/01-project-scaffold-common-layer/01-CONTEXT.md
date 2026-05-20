# Phase 1: Project Scaffold & Common Layer - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

api-service 项目骨架搭建：创建目录结构、合并 common 共享层、统一 Settings 配置类、实现 lifespan 资源管理骨架、提供 /health 和 /ready 端点。不包含任何业务逻辑、数据库连接、或 Redis 初始化（那些在 Phase 2）。

</domain>

<decisions>
## Implementation Decisions

### Common 层合并策略
- **D-01:** 按职责域重新组织 common 层结构，不是简单复制 user-service
- **D-02:** 目录结构为：`common/infra/` (db, redis, cache), `common/security/` (jwt, password, crypto, token_blacklist), `common/http/` (internal_auth, request_context), `common/observability.py`, `common/health.py`, `common/utils/` (nanoid, snowflake, timezone)
- **D-03:** 不迁移 BaseGateway — 合并后无跨服务 HTTP 调用（除 inference-service，由 InferenceClient 自包含）
- **D-04:** internal.py 拆分：Phase 1 只迁移验签部分到 `common/http/internal_auth.py`，调用方逻辑（签名+连接池+熔断）延迟到 Phase 6 在 InferenceClient 中实现
- **D-05:** request_context.py（审计日志 IP/UA 上下文）迁移到 `common/http/`

### Settings 配置合并
- **D-06:** 单一 ApiServiceSettings(BaseServiceSettings) 类 + 注释分区（# --- Database ---, # --- Relay ---, # --- Admin --- 等）
- **D-07:** 环境变量不加服务前缀，直接 DATABASE_URL、REDIS_URL 等。去掉 AliasChoices 兼容逻辑

### 包结构与 import 路径
- **D-08:** 源码根目录为 `api_service/`，启动命令 `uvicorn api_service.main:app`
- **D-09:** 保持 common/ + core/ 分离：common/ 是基础设施层，core/ 是应用级配置（config, dependencies, policies, router, bootstrap, jobs）
- **D-10:** controllers 按角色分子目录：controllers/user/, controllers/admin/, controllers/relay/, controllers/internal/
- **D-11:** services 层：平铺 + services/relay/ 子目录（call_lifecycle, config_cache, channel_selector 等复杂逻辑）
- **D-12:** schemas 按角色分组：schemas/user/, schemas/admin/, schemas/relay/, schemas/common.py
- **D-13:** models 和 repositories 平铺（全局共享，不按域分）

### Lifespan 资源管理
- **D-14:** 渐进式策略 — Phase 1 只初始化基础资源（健康检查所需），后续 Phase 逐步加入
- **D-15:** 使用 LifespanRegistry 注册表模式：register(name, init_fn, shutdown_fn, priority)，按 priority 顺序初始化，关闭时反序
- **D-16:** 初始化失败策略：fail-fast，任何资源失败拒绝启动（已初始化的资源会被清理）
- **D-17:** ARQ Worker 配置延迟到后续 Phase，Phase 1 不包含

### 依赖管理
- **D-18:** 合并三个服务的依赖，去掉 litellm（50MB+），保留直接 openai + anthropic SDK
- **D-19:** 构建工具保持 hatchling + uv，与现有服务一致

### 开发环境
- **D-20:** 开发启动命令：`cd services/api-service && uvicorn api_service.main:app --reload --port 8000`

### 日志配置
- **D-21:** SERVICE_NAME 统一为 "api-service"，LOG_FILE_PREFIX 为 "api-service"

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Migration Plan
- `docs/architecture-refactoring.md` — 完整架构重设计方案，含目标目录结构和分阶段实施计划
- `docs/architecture-refactoring-detail.md` — 详细实现手册，含文件迁移映射表和模块依赖图

### Existing Common Layer (migration source)
- `services/user-service/src/common/` — 最完整的 common 层实现（基础）
- `services/admin-service/src/common/token_blacklist.py` — admin 独有，需迁移
- `services/admin-service/src/common/utils/crypto.py` — admin 独有，需迁移
- `services/admin-service/src/common/request_context.py` — admin 独有，需迁移

### Configuration Reference
- `services/user-service/src/common/config.py` — BaseServiceSettings 基类
- `services/user-service/src/core/config.py` — UserSettings（SMTP_*, CACHE_REDIS_URL）
- `services/admin-service/src/core/config.py` — AdminSettings（BOOTSTRAP_*, PROVIDER_SECRET_MASTER_KEY）
- `services/router-service/src/core/config.py` — RouterSettings（CHANNEL_*, RATE_LIMIT_*, INFERENCE_*, SDK_CLIENT_*)

### Lifespan Pattern
- `services/user-service/src/main.py` — 现有 lifespan 实现参考

### Research Findings
- `.planning/research/STACK.md` — 技术栈建议和版本 pin
- `.planning/research/PITFALLS.md` — 常见陷阱和预防策略

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `user-service/src/common/config.py` BaseServiceSettings: 直接作为新 Settings 的基类
- `user-service/src/common/observability.py`: 完整的结构化日志 + 请求追踪，可直接迁移
- `user-service/src/common/health.py`: build_readiness_response 模式可复用
- `user-service/src/common/db/`: base.py (DeclarativeBase) + runtime.py (engine/session factory) + repository.py (BaseRepository[T])

### Established Patterns
- lifespan 使用 @asynccontextmanager + yield 模式
- Settings 使用 @lru_cache 单例
- 模块级 logger: `logger = logging.getLogger(__name__)`
- 结构化日志: `log_event(logger, level, "eventName", key=value)`
- 异常层级: common/core/exceptions.py 定义基类，各域继承

### Integration Points
- Phase 2 将在 lifespan registry 中注册 DB engine 和 Redis pools
- Phase 3 将 import common/infra/db 和 common/security/jwt
- Phase 6 将在 common/http/ 基础上构建 InferenceClient

</code_context>

<specifics>
## Specific Ideas

- common 层按职责域分组参考了 new-api 的 Go 项目结构（common/infra, common/security, common/http）
- LifespanRegistry 注册表模式：每个模块自注册 init/shutdown，主 lifespan 只调 registry.startup() / registry.shutdown()
- Phase 1 的 /health 只返回静态 JSON，/ready 在 Phase 2 加入 DB/Redis 检查

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 1-Project Scaffold & Common Layer*
*Context gathered: 2026-05-18*
