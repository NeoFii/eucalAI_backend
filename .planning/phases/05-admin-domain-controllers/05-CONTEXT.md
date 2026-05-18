# Phase 5: Admin Domain Controllers - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

将 admin-service 的 13 个 controllers + 9 个 services + 12 个 schemas（共 ~4800 行）迁移到 api-service，**消除所有 admin→user / admin→router HTTP 代理调用**，改为同进程 Python service 直接调用。统一所有 admin 端点路径加 `/api/v1/admin/` 前缀避免与 user 域冲突。

迁移范围对应 ROADMAP success criteria：
1. ADMIN-01: admin login/logout/refresh（独立 Cookie：admin_access_token）
2. ADMIN-03/07/09/10: 5 个原代理 controller 改为直接调用 service 层（user_management / dashboard / vouchers / route_monitor / service_logs）
3. ADMIN-04/05/06: Pool/Channel/Model Catalog/Routing Config CRUD（admin 原生功能）
4. ADMIN-08: 审计日志记录 admin 所有 mutation
5. ADMIN-11: Service Logs 跨服务聚合（本地 RingBuffer + inference HTTP）
6. ADMIN-12: 超管引导初始化

不包含：
- admin 原 `controllers/internal.py` 的 HMAC 内部端点（routing-config / system-settings / admins / model-catalog 内部读）— Phase 8 视需要重建
- admin 原 `controllers/model_catalog.py`（public 读端点 /models /model-vendors 等）— Phase 4 D-06 已由 user 域覆盖
- RoutingConfigCache 实际实现 + 失效订阅逻辑（Phase 6）
- inference-service 端的 HMAC routing-config 接口构造（Phase 8）

</domain>

<decisions>
## Implementation Decisions

### 路径命名空间
- **D-01:** 全部 admin 端点统一加 `/api/v1/admin/` 前缀，**整顿现有路径**：
  - `/api/v1/auth/*`（5 个 admin 端点）→ `/api/v1/admin/auth/*`
  - `/api/v1/users` → `/api/v1/admin/users`
  - `/api/v1/dashboard/*` → `/api/v1/admin/dashboard/*`
  - `/api/v1/vouchers` → `/api/v1/admin/vouchers`
  - `/api/v1/admin-users` → `/api/v1/admin/admin-users`（保持，已含 /admin- 前缀但形式不一致）
  - `/api/v1/admin-audit-logs` → `/api/v1/admin/audit-logs`
  - 原已挂在 `/admin/*` 下的（pools / model_catalog_admin / routing_settings / route_monitor / service_logs）保持不变
- **D-01a:** admin-service `controllers/model_catalog.py`（public 读端点 /models /model-vendors 等）**不迁移** — Phase 4 D-06 已由 user 域覆盖（避免与 `/api/v1/models` 二次注册冲突）
- **D-01b:** admin-service `controllers/internal.py`（HMAC 内部端点）**不迁移** — Phase 5 不引入；Phase 8 视 inference-service 实际需求重建 routing-config 系列。同进程内部不需要 HMAC（沿用 Phase 4 D-01 哲学）
- **D-01c:** 前端兼容性影响：admin 后台前端需更新 API_URL 中的路径前缀（与 PROJECT.md 兼容性约束 "前端路径不变" 不冲突 — 该约束针对用户面前端，admin 前端属另一套，路径整顿可接受）

### 代理消除实现策略
- **D-02:** 新建 admin 域 service 层包装 Phase 4 user services + Phase 3 repositories：
  - 新建 service：
    - `admin/services/admin_user_service.py` — 替代 UserManagementGateway 16 个方法（list/detail/disable/topup/adjust_balance/update_rpm/list_transactions/list_api_keys/disable_api_key/enable_api_key/list_usage_logs/list_usage_stats/get_user_usage_stats/get_user_usage_analytics/reset_password）
    - `admin/services/dashboard_service.py` — 替代 UserStatsGateway 5 个聚合方法（summary/user-growth/usage-trends/rpm-trend/tpm-trend）
    - `admin/services/admin_voucher_service.py` — voucher 兑换码 CRUD（admin 视角）
    - `admin/services/admin_route_monitor_service.py` — relay 监控查询（依赖 CallLogRepository）
    - `admin/services/admin_service_logs_service.py` — 日志聚合（详见 D-03）
  - 迁移既有 service（8 个）：auth_service, audit_service, pool_service, model_catalog_service, routing_setting_service, bootstrap_service, management_service, health_check_service
- **D-02a:** Phase 4 user services（balance_service / api_key_service / voucher_service 等）**保持单一职责**，不增加 `acting_admin_id` 等参数。admin service 直接调用 user service 的现有方法，admin-only 检查在 admin service 层。
- **D-02b:** Audit 日志写入：每个 admin mutation 显式 `await AuditService.record(...)` — 不引入装饰器/middleware 切面（保留显式可读性 + 错误处理灵活）

### Service Logs 数据源
- **D-03:** `/api/v1/admin/service-logs` 实现：
  - 本地 RingBuffer（api-service 进程内）— 覆盖原 admin + user + router 合并后的所有日志
  - HTTP HMAC 调 inference-service `/api/v1/internal/logs/*`（settings.INFERENCE_SERVICE_URL）
  - 删除原 `_REMOTE_SERVICES` 中 user-service / router-service 两条目（消失）
  - 降级行为保留：inference 不可达时返回 partial 结果 + warning
  - 复用 `common.internal.get_internal_client()` HMAC client + `RingBufferHandler`

### 公共 Schema 上移（处理 Phase 4 D-03 延后项）
- **D-04:** 将 `ApiResponse[T]` / `DateTimeModel` / `BaseResponse` / `ErrorResponse` 上移到 `api_service/common/schemas.py`：
  - 合并 user-service `AuthBaseResponse` + admin-service `AdminBaseResponse` 为统一 `BaseResponse`（code + message）
  - `DateTimeModel` 单一实现（两源版本一致）
  - `ApiResponse[T]` 单一实现
  - **Phase 5 同步重构 Phase 4 已写代码**：`from api_service.schemas.common import ...` 改为 `from api_service.common.schemas import ...`
  - `api_service/schemas/common.py` 可删除（推荐）或保留为空壳

### Model Catalog 缓存失效（处理 Phase 4 D-05 延后项）
- **D-05:** admin 写入 model_catalog 时 SCAN+DEL 全量失效 `mc:*` keys：
  - 封装为 `model_catalog_service._invalidate_cache()` 私有方法
  - 在 vendor / category / model / model_category_map 所有 create / update / delete / soft_delete 方法末尾调用
  - 实现：`async for key in redis.scan_iter('mc:*'): await redis.delete(key)`（mc keys 数量上限可控，几十级别）
  - 失效 = 强一致（admin 改后下一次 user 请求重新读 DB + 重填缓存）

### RoutingConfigCache 失效信号（为 Phase 6 纶定接口）
- **D-06:** Phase 5 admin 写 routing_settings 时通过 Redis 版本号信号给 Phase 6 RoutingConfigCache：
  - **契约 key**：`routing_config:version`（Redis db/2 cache 库）
  - **写入方**（Phase 5）：`routing_setting_service.update_setting()` 和 `batch_update()` 末尾执行 `await redis.incr('routing_config:version')`
  - **消费方**（Phase 6）：RoutingConfigCache 每次读时先 `GET routing_config:version` 比对内存版本号；不一致 → reload DB + 更新本地版本；一致 → 用本地缓存。无需 pub/sub 后台订阅任务。
  - 备选：planner 也可改用 `PUBLISH routing_config:invalidate` 模式，但 INCR + poll 实现最简，每次请求 1 次 Redis GET 成本可接受。
  - Phase 5 完成时此 key 已有写入但无消费者，无害。

### Plan 拆分（沿用 ROADMAP）
- **D-07:** 保留 ROADMAP 预定义的 3-plan 拆分，并细化职责：
  - **05-01**: Admin auth + 超管引导
    - controllers/auth.py（5 端点）→ /admin/auth/*
    - services/auth_service.py（259 行）+ bootstrap_service.py（212 行）
    - schemas/auth.py + schemas/admin_user.py + schemas/audit_log.py
    - common/schemas.py 上移（D-04 同步执行）
    - 超管 bootstrap 触发：lifespan 启动钩子 `_bootstrap_super_admin`（幂等）
  - **05-02**: Pool/Channel/Model/Routing config CRUD（admin 原生功能）
    - controllers/pools.py + model_catalog_admin.py + routing_settings.py + admin_users.py + admin_audit_logs.py
    - services/pool_service.py（599 行，最大）+ model_catalog_service.py（535 行）+ routing_setting_service.py（240 行）+ audit_service.py（186 行）+ management_service.py（217 行，admin_users 操作）
    - schemas/pool.py + model_catalog.py（追加写入 schemas）+ routing_setting.py + admin_user.py + audit_log.py
    - **缓存失效集成**：D-05 + D-06 在此 plan 落地
  - **05-03**: 代理消除（user_mgmt / dashboard / vouchers / route_monitor / service_logs）
    - controllers/user_management.py（456 行，最大代理 controller）+ dashboard.py + vouchers.py + route_monitor.py + service_logs.py
    - 新建 admin services：admin_user_service / dashboard_service / admin_voucher_service / admin_route_monitor_service / admin_service_logs_service
    - schemas/user_management.py + route_monitor.py + service_logs.py + voucher.py
    - 删除 `gateways/` 目录（5 个 gateway 全部作废）

### Claude's Discretion
- Service 内 @staticmethod vs 实例方法：沿用 Phase 4 决定，统一 @staticmethod + `db: AsyncSession` 首参（pool_service 599 行较大可内部按 section 组织）
- bootstrap_service 触发时机：建议 lifespan 启动钩子（registry.register("super_admin_bootstrap", ...) priority 较低，在 DB 之后），planner 可酌情改为 CLI 命令
- Audit 写入失败处理：建议 audit 写入失败仅 log warning 不抛异常（不应阻塞业务 mutation 成功）
- D-04 上移过程：Phase 5 第一个 plan（05-01）先执行 schemas 上移 + Phase 4 import 修正，再写新 admin 代码（保证后续 plan 基于新结构）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source Controllers (迁移源 — 13 个文件)
- `services/admin-service/src/controllers/auth.py` — 214 行，5 个 admin auth 端点
- `services/admin-service/src/controllers/admin_users.py` — 126 行，admin 账户管理
- `services/admin-service/src/controllers/admin_audit_logs.py` — 134 行
- `services/admin-service/src/controllers/vouchers.py` — 135 行（代理）
- `services/admin-service/src/controllers/model_catalog_admin.py` — 261 行，CRUD
- `services/admin-service/src/controllers/pools.py` — 231 行
- `services/admin-service/src/controllers/routing_settings.py` — 63 行
- `services/admin-service/src/controllers/service_logs.py` — 63 行（代理）
- `services/admin-service/src/controllers/route_monitor.py` — 142 行（代理）
- `services/admin-service/src/controllers/user_management.py` — 456 行（代理，最大）
- `services/admin-service/src/controllers/dashboard.py` — 198 行（代理）
- **不迁移**：`controllers/model_catalog.py`（96 行，public，Phase 4 D-06 覆盖）
- **不迁移**：`controllers/internal.py`（262 行，Phase 8 视需要重建）

### Source Services (迁移源 — 9 个文件，2700+ 行)
- `services/admin-service/src/services/auth_service.py` — 259 行
- `services/admin-service/src/services/bootstrap_service.py` — 212 行
- `services/admin-service/src/services/management_service.py` — 217 行
- `services/admin-service/src/services/audit_service.py` — 186 行
- `services/admin-service/src/services/pool_service.py` — 599 行（最大）
- `services/admin-service/src/services/model_catalog_service.py` — 535 行
- `services/admin-service/src/services/routing_setting_service.py` — 240 行
- `services/admin-service/src/services/health_check_service.py` — 173 行

### Source Schemas (迁移源 — 12 个文件)
- `services/admin-service/src/schemas/auth.py`
- `services/admin-service/src/schemas/admin_user.py`
- `services/admin-service/src/schemas/audit_log.py`
- `services/admin-service/src/schemas/common.py` — D-04 上移到 common/schemas.py
- `services/admin-service/src/schemas/model_catalog.py` — Phase 4 D-06 已迁读 schemas，Phase 5 追加写入 schemas
- `services/admin-service/src/schemas/pool.py`
- `services/admin-service/src/schemas/route_monitor.py`
- `services/admin-service/src/schemas/routing_setting.py`
- `services/admin-service/src/schemas/service_logs.py`
- `services/admin-service/src/schemas/user_management.py`
- `services/admin-service/src/schemas/voucher.py`

### Source Gateways (将被消除，迁移时作为映射参考)
- `services/admin-service/src/gateways/user_management.py` — UserManagementGateway 16 方法 → admin_user_service
- `services/admin-service/src/gateways/route_monitor.py` → admin_route_monitor_service
- `services/admin-service/src/gateways/service_logs.py` — _REMOTE_SERVICES 删 user/router，保 inference
- `services/admin-service/src/gateways/dashboard.py`（若存在）→ dashboard_service

### Phase 3 产出（已就绪 — admin 域 repository）
- `services/api-service/api_service/repositories/admin_user_repository.py` — AdminUserRepository
- `services/api-service/api_service/repositories/audit_log_repository.py` — AuditLogRepository
- `services/api-service/api_service/repositories/pool_repository.py` — pool + pool_model_config + pool_account 合并
- `services/api-service/api_service/repositories/model_catalog_repository.py` — vendor + category + model + map
- `services/api-service/api_service/repositories/routing_setting_repository.py` — RoutingSettingRepository
- `services/api-service/api_service/repositories/call_log_repository.py` — CallLogRepository（含 route_monitor 查询）

### Phase 3 产出（admin auth 依赖）
- `services/api-service/api_service/core/dependencies/admin.py` — `get_current_admin`, `get_optional_current_admin`, `get_request_meta`（Phase 3 D-06/D-07）
- 含 token blacklist 检查（D-07）

### Phase 4 产出（user services — admin 包装层依赖）
- `services/api-service/api_service/services/auth_service.py` — user 域
- `services/api-service/api_service/services/balance_service.py` — 余额操作（admin 调用做充值/调账）
- `services/api-service/api_service/services/api_key_service.py` — admin 调用做禁用/启用
- `services/api-service/api_service/services/voucher_service.py` — admin 调用做兑换码 CRUD
- `services/api-service/api_service/services/usage_stat_service.py` — dashboard 聚合查询
- `services/api-service/api_service/schemas/model_catalog.py` — Phase 4 已含读 schemas，Phase 5 追加写

### Phase 2 产出（infra — admin 依赖）
- `services/api-service/api_service/core/db.py` — `get_db` 依赖
- `services/api-service/api_service/core/redis_pools.py` — 三 Redis pool（session db/0、arq db/1、cache db/2）
- `services/api-service/api_service/common/internal.py` — HMAC client / `get_internal_client()`
- `services/api-service/api_service/common/observability.py` — `RingBufferHandler`, `log_event`

### Architecture / 项目约束
- `docs/architecture-refactoring.md` — 合并架构方案（admin→user 代理消除）
- `services/admin-service/CLAUDE.md`（若存在）— admin 域规范
- `services/user-service/CLAUDE.md` — service 层 @staticmethod 规范（同样适用 admin 域）
- `CLAUDE.md`（root）— user_uid 对外、user_id 内部规范

### Phase 4 已落实决策（避免回溯重提）
- `.planning/phases/04-user-domain-controllers/04-CONTEXT.md` — Phase 4 D-01~D-08
  - D-01: internal_*.py 不迁移（Phase 5 admin 同进程直接调用，验证此假设）
  - D-03: schemas/common.py 暂存 → D-04 在 Phase 5 上移
  - D-05: mc:* 缓存失效 → D-05 在 Phase 5 实现
  - D-06/D-07: model_catalog 读 schemas 已迁，Phase 5 补写 schemas

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 3 全部 admin 域 repositories（6 个，已合并 pool 域）
- `get_current_admin` 依赖（Phase 3 D-06，含 token blacklist 检查）
- `RingBufferHandler` + `get_ring_buffer()` 已在 api-service common/observability.py
- HMAC client `get_internal_client()` + `verify_internal_secret` 已在 common.internal
- `common.cache.cache_get_or_fetch` 已就绪（mc: cache 使用）
- Redis pool db/2 已就绪（mc: + routing_config:version）

### Established Patterns
- Controller 薄层 + Depends(get_current_admin) + Depends(get_db)
- Service @staticmethod + AsyncSession 首参
- Audit log 写入：当前 admin-service 在 mutation 后显式调用 `AuditService.record()`
- bootstrap 模式：lifespan 启动钩子幂等创建超管账户
- Snowflake ID worker_id=2（admin 域）— Phase 2 已配置

### Integration Points
- `api_service/core/router.py` — Phase 5 admin 路由注册（推荐用 `api_router.include_router(admin_router, prefix='/admin')` 一次性挂全部 admin 子路由）
- `api_service/core/lifespan.py` — 注册 super_admin_bootstrap 钩子
- `api_service/common/schemas.py` — D-04 新建，集中公共 schema
- Cookie 名：`admin_access_token` / `admin_refresh_token`（与 user 完全独立）

### 已识别风险点
- **D-01 路径整顿对 admin 前端影响**：admin 前端需更新所有 API_URL。需 Phase 9 集成测试时同步前端联调；如果 admin 前端不在本仓库，需协调发布顺序（admin 前端先准备好新 URL，api-service 切换后立即生效）
- **D-04 上移涉及 Phase 4 import 修正**：05-01 plan 第一步执行，否则后续 plan 中 admin schemas import 上移后会引起 user schemas 重复定义冲突
- **D-05 SCAN 性能**：mc:* keys 数量预期 < 50，SCAN MATCH+iter 单次 admin 写入耗时 < 10ms，可接受
- **D-06 RoutingConfigCache 版本号读取频率**：Phase 6 实现时每 relay 请求做一次 GET routing_config:version；Redis db/2 cache 库延迟 < 1ms，4 worker × 100 req/s = 400 GET/s 远低于 Redis 阈值
- **bootstrap 与 DB ready 顺序**：lifespan 钩子 priority 必须晚于 DB engine 初始化（priority > 20）
- **/admin/users 等 admin 端点**：D-01 后 `/api/v1/admin/users` 与 user 域无冲突，但需确认 admin 前端代码 URL 已更新

</code_context>

<specifics>
## Specific Ideas

- admin auth 路径：`/api/v1/admin/auth/login` `/logout` `/refresh` `/me` `/change-password`（5 个）
- Cookie name 严格区分：`admin_access_token` / `admin_refresh_token`，path 设为 `/api/v1/admin`（限制范围）
- Audit log 字段：actor_admin_uid、action_type、target_user_uid（可选）、payload_snapshot（关键字段）、result_status、occurred_at、request_id（用于关联）
- Super admin bootstrap：环境变量 ADMIN_BOOTSTRAP_USERNAME + ADMIN_BOOTSTRAP_PASSWORD（仅首次启动有用户名匹配时建立）
- dashboard summary 聚合应单次查询 + JOIN（避免 N+1）；其他 trends 类查询走 UsageStatRepository 按时间窗
- pool_service 内部按 section 组织：pool CRUD / pool_model_config CRUD / pool_account CRUD（建议三个内嵌类或显式区段注释）
- `_invalidate_cache()` 应在 service 层 commit 后调用，避免 commit 失败时也清缓存（缓存清空虽然安全但增加 DB 压力）
- service_logs 端点支持 `services=['api-service', 'inference-service']` 参数过滤（保留原 query 接口形态）

</specifics>

<deferred>
## Deferred Ideas

- **HMAC 内部端点骨架**：Phase 8 重建 `/api/v1/internal/routing-config/active/{full,inference}` 等供 inference-service 拉取配置。Phase 5 不预留。
- **集中日志系统接入**（ELK / Loki）：超出本次重构，长期可考虑替代 RingBuffer。
- **Audit log 装饰器/middleware 切面**：D-02b 选择显式写入，未来如果 mutation 数量增长可考虑统一切面，留作长期优化。
- **超管 bootstrap CLI 命令**：D-07 选 lifespan 触发，如有运维场景需要在不启动 app 时建立超管，可补 CLI（不在本次范围）。
- **dashboard 聚合查询缓存**：dashboard 5 端点都是聚合查询，TPS 不高但单次成本高，可加 30s 缓存。本次不引入避免缓存失效复杂度，性能不达标时 Phase 9 评估。
- **RoutingConfigCache 失效改 PUBLISH**：D-06 选 INCR + poll，长期可改 pub/sub 减少 Redis GET 次数。Phase 6 实现时再评估。

</deferred>

---

*Phase: 5-Admin Domain Controllers*
*Context gathered: 2026-05-19*
