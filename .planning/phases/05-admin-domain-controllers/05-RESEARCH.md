# Phase 5: Admin Domain Controllers - Research

**Researched:** 2026-05-19
**Domain:** Migration / refactor — port 13 admin-service controllers + 9 services + 12 schemas (~4800 lines) into the merged api-service; eliminate ALL admin→user / admin→router HTTP gateway calls (5 gateways) and replace with same-process Python service calls. Unify path namespace under `/api/v1/admin/`.
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 路径命名空间

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

#### 代理消除实现策略

- **D-02:** 新建 admin 域 service 层包装 Phase 4 user services + Phase 3 repositories：
  - 新建 service：
    - `admin/services/admin_user_service.py` — 替代 UserManagementGateway 16 个方法
    - `admin/services/dashboard_service.py` — 替代 UserStatsGateway 5 个聚合方法
    - `admin/services/admin_voucher_service.py` — voucher 兑换码 CRUD（admin 视角）
    - `admin/services/admin_route_monitor_service.py` — relay 监控查询（依赖 CallLogRepository）
    - `admin/services/admin_service_logs_service.py` — 日志聚合（详见 D-03）
  - 迁移既有 service（8 个）：auth_service, audit_service, pool_service, model_catalog_service, routing_setting_service, bootstrap_service, management_service, health_check_service
- **D-02a:** Phase 4 user services 保持单一职责，不增加 `acting_admin_id` 参数。admin service 直接调用 user service 现有方法，admin-only 检查在 admin service 层。
- **D-02b:** Audit 日志写入：每个 admin mutation 显式 `await AuditService.record(...)` — 不引入装饰器/middleware 切面（保留显式可读性 + 错误处理灵活）

#### Service Logs 数据源

- **D-03:** `/api/v1/admin/service-logs` 实现：
  - 本地 RingBuffer（api-service 进程内）— 覆盖原 admin + user + router 合并后的所有日志
  - HTTP HMAC 调 inference-service `/api/v1/internal/logs/*`（settings.INFERENCE_SERVICE_URL）
  - 删除原 `_REMOTE_SERVICES` 中 user-service / router-service 两条目（消失）
  - 降级行为保留：inference 不可达时返回 partial 结果 + warning
  - 复用 `common.internal.get_internal_client()` HMAC client + `RingBufferHandler`

#### 公共 Schema 上移（处理 Phase 4 D-03 延后项）

- **D-04:** 将 `ApiResponse[T]` / `DateTimeModel` / `BaseResponse` / `ErrorResponse` 上移到 `api_service/common/schemas.py`：
  - 合并 user-service `AuthBaseResponse` + admin-service `AdminBaseResponse` 为统一 `BaseResponse`（code + message）
  - `DateTimeModel` 单一实现（两源版本一致）
  - `ApiResponse[T]` 单一实现
  - **Phase 5 同步重构 Phase 4 已写代码**：`from api_service.schemas.common import ...` 改为 `from api_service.common.schemas import ...`
  - `api_service/schemas/common.py` 可删除（推荐）或保留为空壳

#### Model Catalog 缓存失效（处理 Phase 4 D-05 延后项）

- **D-05:** admin 写入 model_catalog 时 SCAN+DEL 全量失效 `mc:*` keys：
  - 封装为 `model_catalog_service._invalidate_cache()` 私有方法
  - 在 vendor / category / model / model_category_map 所有 create / update / delete / soft_delete 方法末尾调用
  - 实现：`async for key in redis.scan_iter('mc:*'): await redis.delete(key)`（mc keys 数量上限可控，几十级别）
  - 失效 = 强一致（admin 改后下一次 user 请求重新读 DB + 重填缓存）

#### RoutingConfigCache 失效信号（为 Phase 6 纶定接口）

- **D-06:** Phase 5 admin 写 routing_settings 时通过 Redis 版本号信号给 Phase 6 RoutingConfigCache：
  - **契约 key**：`routing_config:version`（Redis db/2 cache 库）
  - **写入方**（Phase 5）：`routing_setting_service.update_setting()` 和 `batch_update()` 末尾执行 `await redis.incr('routing_config:version')`
  - **消费方**（Phase 6）：RoutingConfigCache 每次读时先 `GET routing_config:version` 比对内存版本号
  - 备选：planner 可改用 `PUBLISH routing_config:invalidate` 模式，但 INCR + poll 实现最简
  - Phase 5 完成时此 key 已有写入但无消费者，无害。

#### Plan 拆分（沿用 ROADMAP）

- **D-07:** 保留 ROADMAP 预定义的 3-plan 拆分：
  - **05-01**: Admin auth + 超管引导（controllers/auth.py, services/auth_service.py + bootstrap_service.py, schemas/{auth,admin_user,audit_log,common}.py，**先执行 D-04 上移 + 修正 Phase 4 imports**）
  - **05-02**: Pool/Channel/Model/Routing config CRUD（含 D-05 + D-06 缓存失效落地）
  - **05-03**: 代理消除（user_mgmt / dashboard / vouchers / route_monitor / service_logs，**删除 gateways/ 目录**）

### Claude's Discretion

- Service 内 @staticmethod vs 实例方法：沿用 Phase 4 决定，统一 @staticmethod + `db: AsyncSession` 首参（pool_service 599 行较大可内部按 section 组织）
- bootstrap_service 触发时机：建议 lifespan 启动钩子（registry.register("super_admin_bootstrap", ...) priority 较低，在 DB 之后），planner 可酌情改为 CLI 命令
- Audit 写入失败处理：建议 audit 写入失败仅 log warning 不抛异常（不应阻塞业务 mutation 成功）
- D-04 上移过程：Phase 5 第一个 plan（05-01）先执行 schemas 上移 + Phase 4 import 修正，再写新 admin 代码（保证后续 plan 基于新结构）

### Deferred Ideas (OUT OF SCOPE)

- **HMAC 内部端点骨架**：Phase 8 重建 `/api/v1/internal/routing-config/active/{full,inference}` 等。Phase 5 不预留。
- **集中日志系统接入**（ELK / Loki）：超出本次重构。
- **Audit log 装饰器/middleware 切面**：D-02b 选择显式写入，未来如果 mutation 数量增长可考虑切面。
- **超管 bootstrap CLI 命令**：D-07 选 lifespan 触发，如有运维场景需要在不启动 app 时建立超管可补 CLI。
- **dashboard 聚合查询缓存**：5 端点都是聚合查询，本次不引入避免缓存失效复杂度。
- **RoutingConfigCache 失效改 PUBLISH**：D-06 选 INCR + poll，长期可改 pub/sub。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADMIN-01 | 管理员登录/登出/刷新 token 端点正常工作 | `controllers/auth.py` + `services/auth_service.py` + cookie scoping pattern (D-01); separate `admin_access_token` cookie path locked in CONTEXT |
| ADMIN-03 | 用户管理端点直接调用 service 层（不再 HTTP 代理） | D-02 — new `admin_user_service.py` wraps `BalanceService`/`ApiKeyService`/`UserRepository`; replaces 16 `UserManagementGateway` methods |
| ADMIN-04 | Pool/Channel CRUD 端点正常工作 | `controllers/pools.py` (231 lines) + `services/pool_service.py` (599 lines, largest) + `repositories/pool_repository.py` already merged (Phase 3) |
| ADMIN-05 | 模型目录 CRUD 端点正常工作 | `controllers/model_catalog_admin.py` + `services/model_catalog_service.py` (535 lines); D-05 cache invalidation lands here |
| ADMIN-06 | 路由配置管理端点正常工作 | `controllers/routing_settings.py` (63 lines, smallest) + `services/routing_setting_service.py`; D-06 `routing_config:version` INCR lands here |
| ADMIN-07 | 仪表盘统计端点直接调用 service 层（不再 HTTP 代理） | D-02 — new `dashboard_service.py` replaces 5 `UserStatsGateway` methods; aggregations via `BillingRepository.stat_*` + `CallLogRepository.aggregate_metrics` |
| ADMIN-08 | 审计日志端点正常工作 | `controllers/admin_audit_logs.py` + `services/audit_service.py` (186 lines); D-02b explicit `await AuditService.record(...)` after each mutation |
| ADMIN-09 | 兑换码管理端点直接调用 service 层（不再 HTTP 代理） | D-02 — new `admin_voucher_service.py` calls `VoucherService` (Phase 4) for generate/list/get/disable |
| ADMIN-10 | Route Monitor 端点直接调用 service 层（不再 HTTP 代理） | D-02 — new `admin_route_monitor_service.py` calls `CallLogRepository` (Phase 3) directly; eliminates `RouteMonitorGateway` |
| ADMIN-11 | Service Logs 查询端点正常工作 | D-03 — RingBuffer (in-process, Phase 1) + HMAC HTTP to inference-service only; user/router removed from `_REMOTE_SERVICES` |
| ADMIN-12 | 超管引导初始化正常工作 | `services/bootstrap_service.py` (212 lines); MySQL `GET_LOCK` for cross-worker exclusion; lifespan registration priority > 20 (post-DB) |

ADMIN-02 (admin JWT cookie 鉴权) was satisfied by Phase 3 (`core/dependencies/admin.py`). Phase 5 just *consumes* `get_current_admin` / `get_optional_current_admin`.
</phase_requirements>

## Summary

This phase is a **port + dual-purpose consolidation**: (1) move 13 admin controllers + 9 services + 12 schemas into the merged api-service, and (2) **eliminate every cross-service HTTP call** (5 gateways: `UserManagementGateway`, `UserStatsGateway`, `RouteMonitorGateway`, `ServiceLogsGateway`, and the unused gateway-based proxy in `vouchers.py`). The admin domain becomes a thin set of CRUD/audit wrappers on top of Phase 3 repositories and Phase 4 user services.

The mechanical scope is similar to Phase 4 (which the planner can mirror), but Phase 5 adds three structural concerns Phase 4 deferred: schema consolidation under `common/schemas.py` (D-04), `mc:*` cache invalidation (D-05), and `routing_config:version` Redis signal (D-06). The riskiest single artifact is `pool_service.py` (599 lines, in-place encrypt/decrypt of provider API keys, real upstream HTTP balance checks); the riskiest single workflow is the `safe_audit_commit` pattern — 14+ controller call sites today, each of which becomes an explicit `await AdminAuditService.record(...)` + `await db.commit()` block per D-02b.

**Primary recommendation:** Plan 05-01 is gating. It must (a) hoist `common/schemas.py`, (b) rewrite Phase 4's `from api_service.schemas.common import` imports across all Phase 4 files, (c) port admin auth + bootstrap, (d) port the bare `AdminAuditService` (because Plans 05-02 and 05-03 both depend on `await AdminAuditService.record(...)` in every mutating endpoint). Without (d) the later plans cannot wire audit calls.

**Pre-flight blocker (Phase 4 dependency):** Phase 5 cannot start until Phase 4 has at minimum landed Wave 0 + schemas/common.py + `core/arq_pool.py` + the auth/balance/api_key/voucher/usage_stat services. The admin user-management/voucher/dashboard services in 05-03 call directly into Phase 4's `BalanceService`, `ApiKeyService`, `VoucherService`, `UsageStatService`. The planner must verify Phase 4 completion before starting 05-03, or stub the missing services and treat 05-03 as blocked.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Admin login / refresh / change-password | API / Backend (`controllers/admin/auth.py` + `AdminAuthService`) | Database (`admin_users`, `admin_audit_logs`) | Stateless JWT + DB row for `login_fail_count` / `login_locked_until` |
| Admin token blacklist (logout) | API / Backend (`AdminAuthService.logout`) | Cache / Storage (Redis db/0) | `blacklist_token(jti, ttl)` — Phase 3 D-07 retains admin blacklist; user side does not |
| Admin cookie set/clear | API / Backend (controller cookie helpers) | — | `admin_access_token` / `admin_refresh_token` with path `/` (D-01 directs path stays `/` for Next.js middleware; cookie name is the namespacing axis, NOT path) |
| Super admin bootstrap | API / Backend (`AdminBootstrapService`) | Database (`GET_LOCK` named lock) | Lifespan startup hook, idempotent — MySQL named lock prevents concurrent workers from double-creating |
| Audit log write | API / Backend (`AdminAuditService.record`) | Database (`admin_audit_logs`) | D-02b — explicit call per mutation, no decorator. Failure logged but does NOT block the mutation (per CONTEXT discretion) |
| Audit action label cache | API / Backend (module-level dict in `audit_service.py`) | Database (`audit_action_definitions`) | Per-process cache; cleared on label update |
| Pool / Pool Account / Pool Model CRUD | API / Backend (`PoolService`) | Database (`pools`, `pool_accounts`, `pool_model_configs`) + External upstream HTTP | Pool service does AES-GCM encrypt of provider API key + calls upstream `/v1/balance` endpoints via `get_internal_client` |
| Provider API-key encryption at rest | API / Backend (`PoolService._encrypt_api_key`) | Database (`pool_accounts.api_key_enc`) | AES-256-GCM via `common/security/crypto.py` (already migrated in Phase 1) |
| Model catalog CRUD (vendor/category/model) | API / Backend (`ModelCatalogService`) | Database + Cache (Redis db/2) | D-05 cache SCAN/DEL on every write — `mc:*` keys touched |
| Routing settings CRUD | API / Backend (`RoutingSettingService`) | Database (`routing_settings`) + Cache (Redis db/2 `routing_config:version`) | D-06 INCR on update/batch_update; Phase 6 consumes the version |
| Routing config validation (tier model coverage) | API / Backend (`RoutingSettingService.validate_tier_model_coverage`) | Database (`pools` JOIN `pool_model_configs` JOIN `model_catalog`) | Pre-write check ensures tier_N_model has both pool coverage AND catalog `routing_slug` |
| User management proxy (list/detail/topup/adjust/disable/RPM/reset-password) | API / Backend (`AdminUserService` — NEW) | Database via Phase 4 user services | D-02 wraps `BalanceService`, `ApiKeyService`, `UserRepository` — eliminates 16-method gateway |
| Dashboard aggregations (summary/user-growth/usage-trends/rpm-trend/tpm-trend) | API / Backend (`AdminDashboardService` — NEW) | Database via `BillingRepository.stat_*` + new aggregate helpers | D-02 — 5 new methods directly on repos; eliminates 5-method gateway |
| Voucher admin CRUD | API / Backend (`AdminVoucherService` — NEW) | Database via Phase 4 `VoucherService` | D-02 — wraps Phase 4 voucher service for admin perspective (generate batch / list / get / disable) |
| Route monitor list/detail/aggregates/compare | API / Backend (`AdminRouteMonitorService` — NEW) | Database via `CallLogRepository` (Phase 3) | D-02 — directly calls `call_log_repository.list_requests/get_request_detail/find_same_input_siblings/aggregate_metrics` |
| Service logs aggregation | API / Backend (`AdminServiceLogsService` — NEW) | Local RingBuffer + HTTP to inference-service | D-03 — local RingBuffer covers admin+user+router (all merged); only inference is remote |
| HMAC client to inference-service | API / Backend (`common/internal.py` — NEW for api-service) | External HTTP | **Phase 5 prerequisite — see Pitfall 1 below.** Module must be ported from admin-service before D-03 can land |
| Health check service (channel probing) | Background process (ARQ worker) | Database + External HTTP + Cache | `HealthCheckService.run_health_checks` — currently called via ARQ cron in admin-service. Phase 5 ports the service module but **not** the cron registration (deferred to a future plan; admin-service had this as cron, Phase 4's ARQ worker can pick it up but planner must explicitly add it) |
| Admin user account management (admin-on-admin CRUD) | API / Backend (`AdminManagementService`) | Database (`admin_users`) | Distinct from `AdminUserService` (which manages end users) — naming will collide; planner must rename one. Recommend: `AdminUserService` → user-facing-admin operations; `AdminAccountService` → admin-on-admin CRUD |

## Standard Stack

All dependencies already declared in `services/api-service/pyproject.toml` (verified in Phase 4 research). No new installs in Phase 5.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.115.0 | HTTP framework | `[VERIFIED: Phase 4 RESEARCH.md]` |
| pydantic | >=2.5.0 | Schema validation, generic `ApiResponse[T]` | `[VERIFIED: Phase 4 RESEARCH.md]` |
| sqlalchemy[asyncio] | >=2.0.25 | Async ORM | `[VERIFIED: Phase 4 RESEARCH.md]` |
| aiomysql | >=0.2.0 | MySQL driver — used by `MySQL GET_LOCK` for bootstrap | `[VERIFIED]` |
| redis | >=5.0 | `scan_iter` for D-05 + `incr` for D-06 | `[VERIFIED]` |
| python-jose[cryptography] | >=3.3.1 | JWT for admin tokens | `[VERIFIED]` |
| passlib[bcrypt] | >=1.7.4 | Admin password hashing | `[VERIFIED]` |
| httpx | >=0.26.0 | HMAC client → inference-service (D-03) | `[VERIFIED]` |
| cryptography | >=42.0.0 | AES-256-GCM for `pool_accounts.api_key_enc` (already in `common/security/crypto.py`) | `[VERIFIED: api_service/common/security/crypto.py]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` (stdlib) | — | sha256 for JWT JTI | All admin auth operations |
| `secrets` (stdlib) | — | Bootstrap password generation if `BOOTSTRAP_SUPERADMIN_PASSWORD` is left blank | One-time bootstrap |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| MySQL `GET_LOCK` for bootstrap exclusion | Redis `SETNX` lock | Bootstrap runs once at startup; MySQL lock is in the same connection as the DB write — cleaner atomicity. Source already uses this pattern. **Keep.** |
| Redis `SCAN MATCH 'mc:*'` for D-05 | Maintain a Redis Set of keys (`mc:keys`) and iterate | SCAN with ~50 keys is < 5ms; the Set approach adds write-side bookkeeping for no gain. **Use SCAN.** |
| Redis pub/sub for D-06 routing config invalidation | INCR + GET poll | INCR + GET is one network round trip per relay request (~0.5ms). Pub/sub requires a background subscriber task — more moving parts. **Use INCR.** D-06 explicitly notes this. |
| Audit middleware decorator | Explicit `await AuditService.record(...)` | D-02b locks explicit. **Keep explicit.** |

**Installation:**
```bash
# No new installs. Verified via Phase 4 research and pyproject.toml read.
```

**Version verification:** No new versions to verify — Phase 5 reuses Phase 1–4 baseline.

## Package Legitimacy Audit

> No new packages are installed in Phase 5. All dependencies originate from Phase 1 (`pyproject.toml` baseline) and were audited there. The legitimacy gate is **N/A** for this phase.

| Package | Registry | Disposition |
|---------|----------|-------------|
| (all) | PyPI | Already approved in Phase 1 |

## Architecture Patterns

### System Architecture Diagram

```
Admin Next.js Frontend
   │
   │  Cookie: admin_access_token  (HttpOnly, SameSite=strict, path="/")
   │  Cookie: admin_refresh_token (HttpOnly, SameSite=strict, path="/")
   │
   │  All admin requests → /api/v1/admin/*
   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ FastAPI controllers (api_service/controllers/admin/*)                       │
│   • Mounted via api_router.include_router(admin_router, prefix="/admin")    │
│   • Depends(get_current_admin) or Depends(require_super_admin)              │
│   • Cookie helpers identical to Phase 4 pattern, only token names differ    │
└──────┬──────────────────────────────────────────────────┬───────────────────┘
       │                                                  │
       │  Native admin services                           │  Proxy-elimination services
       ▼                                                  ▼
┌──────────────────────────────────┐         ┌────────────────────────────────────────┐
│ AdminAuthService                 │         │ AdminUserService          (replaces    │
│ AdminBootstrapService            │         │                            UserMgmtGW) │
│ AdminManagementService           │         │ AdminDashboardService     (replaces    │
│ AdminAuditService                │         │                            UserStatsGW)│
│ PoolService                      │         │ AdminVoucherService       (replaces    │
│ ModelCatalogService              │         │                            VoucherGW)  │
│ RoutingSettingService            │         │ AdminRouteMonitorService  (replaces    │
│ HealthCheckService               │         │                            RtMonGW)    │
│                                  │         │ AdminServiceLogsService   (replaces    │
│                                  │         │                            SvcLogsGW)  │
└──────┬─────┬─────┬───────────────┘         └───────┬──────────┬──────────────┬─────┘
       │     │     │                                 │          │              │
       │     │     │  call into Phase 3 repos        │ delegate │              │ HMAC
       │     │     │                                 │ to       │ direct       │ HTTP
       │     │     │                                 │ Phase 4  │ Phase 3      │
       ▼     ▼     ▼                                 ▼          ▼              ▼
┌──────────────────────┐  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Phase 3 repositories │  │ Phase 4     │  │ CallLogRepository│  │ inference-service│
│  • AdminUserRepo     │  │ services:   │  │ BillingRepository│  │ /api/v1/internal/│
│  • AuditLogRepo      │  │  Balance    │  │ (stat_*, joins)  │  │     logs         │
│  • PoolRepo          │  │  ApiKey     │  │                  │  │ HMAC signed      │
│  • ModelCatalogRepo  │  │  Voucher    │  │                  │  │                  │
│  • RoutingSettingRepo│  │  UsageStat  │  │                  │  │                  │
└──────────┬───────────┘  └──────┬──────┘  └────────┬─────────┘  └──────────────────┘
           │                     │                  │
           ▼                     ▼                  ▼
        MySQL eucal_ai DB  ◄── shared single engine, no second connection
                                      │
                                      ▼
                              Redis db/2 (cache)
                                  │
                                  ├── mc:* keys ← D-05 SCAN/DEL on every admin model_catalog write
                                  └── routing_config:version ← D-06 INCR on every routing_settings write

                              Local RingBuffer (Phase 1, common/observability.py)
                                  │
                                  └── _fetch_local() — covers api-service's own logs (merged scope)

                              Bootstrap (lifespan priority > 20, after DB):
                                  GET_LOCK("bootstrap_super_admin") → upsert super_admin → audit
```

**Reading the diagram:** Admin auth flows through cookie + `get_current_admin` (Phase 3); all mutations go service → repository → DB with an explicit `await AdminAuditService.record(...)` written into each mutation method. The five "proxy-elimination" services are NEW (replacing five `gateways/*.py` files that get deleted in 05-03). The cache invalidation paths (`mc:*` and `routing_config:version`) are the cross-domain contracts the planner must wire deterministically.

### Component Responsibilities

| File (target path) | Responsibility | Source Lines |
|--------------------|----------------|--------------|
| `api_service/common/schemas.py` (NEW per D-04) | Hoisted `ApiResponse[T]`, `DateTimeModel`, `BaseResponse`, `ErrorResponse` | merge of user `schemas/common.py` (40) + admin `schemas/common.py` (35) |
| `api_service/controllers/admin/__init__.py` (NEW) | `admin_router = APIRouter(prefix="/admin")` + `include_router` for each sub-router | ~15 |
| `api_service/controllers/admin/auth.py` | 5 endpoints: login/logout/refresh/me/change-password | 214 |
| `api_service/controllers/admin/admin_users.py` | 5 endpoints: list/create/status/reset-password/role (admin-on-admin) | 126 |
| `api_service/controllers/admin/audit_logs.py` | 3 endpoints: meta/list/update-label | 134 |
| `api_service/controllers/admin/pools.py` | 16 endpoints: pool/pool_model/pool_account CRUD + balance check + sync | 231 |
| `api_service/controllers/admin/model_catalog.py` (admin write) | 9 endpoints: vendors/categories/models CRUD + archive | 261 |
| `api_service/controllers/admin/routing_settings.py` | 3 endpoints: list/batch_update/update | 63 |
| `api_service/controllers/admin/users.py` (proxy → native) | 14 endpoints: list/detail/status/reset-password/topup/adjust/RPM/transactions/api-keys/usage-logs/usage-stats | 456 |
| `api_service/controllers/admin/dashboard.py` (proxy → native) | 5 endpoints: summary/user-growth/usage-trends/rpm-trend/tpm-trend | 198 |
| `api_service/controllers/admin/vouchers.py` (proxy → native) | 4 endpoints: generate/list/get/disable | 135 |
| `api_service/controllers/admin/route_monitor.py` (proxy → native) | 4 endpoints: requests/detail/aggregates/compare | 142 |
| `api_service/controllers/admin/service_logs.py` (proxy → partial native) | 1 endpoint: aggregate logs | 63 |
| `api_service/services/admin/auth_service.py` | `login`/`logout`/`refresh_access_token`/`change_password`/`get_current_admin` | 259 |
| `api_service/services/admin/bootstrap_service.py` | `ensure_super_admin` + MySQL `GET_LOCK` + idempotent upsert | 212 |
| `api_service/services/admin/management_service.py` | Admin-on-admin: `list_admins`/`create_admin`/`update_admin_status`/`reset_admin_password`/`update_admin_role` | 217 |
| `api_service/services/admin/audit_service.py` | `record`/`record_auto`/`list_logs`/`get_meta`/`update_action_label` + module cache | 186 |
| `api_service/services/admin/pool_service.py` | Pool/PoolModelConfig/PoolAccount CRUD + AES encrypt + upstream balance check | 599 |
| `api_service/services/admin/model_catalog_service.py` | Vendor/category/model CRUD + D-05 cache invalidation | 535 + ~10 (cache invalidation hook) |
| `api_service/services/admin/routing_setting_service.py` | list/get/update/batch_update + D-06 `routing_config:version` INCR + tier coverage validation | 240 + ~5 |
| `api_service/services/admin/health_check_service.py` | Channel-balance probing (currently cron-driven; Phase 5 ports module, planner decides cron timing) | 173 |
| `api_service/services/admin/admin_user_service.py` (NEW per D-02) | 16 methods replacing `UserManagementGateway`: list/detail/disable/topup/adjust/RPM/transactions/api-keys/usage logs/stats/analytics/reset-password | ~400 |
| `api_service/services/admin/dashboard_service.py` (NEW per D-02) | 5 methods: summary/user-growth/usage-trends/rpm-trend/tpm-trend | ~200 |
| `api_service/services/admin/voucher_service.py` (NEW per D-02) | 4 methods: generate/list/get/disable (admin-perspective wrapper over Phase 4 `VoucherService`) | ~120 |
| `api_service/services/admin/route_monitor_service.py` (NEW per D-02) | 4 methods: list_requests/get_request_detail/get_aggregates/get_compare → calls `CallLogRepository` | ~150 |
| `api_service/services/admin/service_logs_service.py` (NEW per D-03) | 1 method: `fetch_all(services, level, since, until, search, after_seq, page, page_size)` — local RingBuffer + HMAC HTTP to inference | ~120 |
| `api_service/common/internal.py` (NEW — see Pitfall 1) | HMAC client `get_internal_client`/`get_internal_json` + circuit breaker | port from admin-service `common/internal.py` (552 lines) |
| `api_service/schemas/admin/__init__.py` (NEW) | Export aggregator for `from api_service.schemas.admin import ...` | ~80 |
| `api_service/schemas/admin/auth.py` | AdminLogin/AdminLogout/AdminRefresh/AdminInfo/AdminChangePassword Request+Response | 108 |
| `api_service/schemas/admin/admin_user.py` | AdminListItem/AdminListResponse/CreateAdminRequest/UpdateAdminStatusRequest etc. | 142 |
| `api_service/schemas/admin/audit_log.py` | AdminAuditActor/AdminAuditLogItem/AdminAuditCategory literal/UpdateActionLabelRequest | 80 |
| `api_service/schemas/admin/pool.py` | PoolCreate/PoolUpdate/PoolItem/PoolDetail/PoolModelCreate/PoolAccountCreate etc. | 229 |
| `api_service/schemas/admin/model_catalog.py` | EXTEND Phase 4 read schemas with write schemas: ModelVendorCreate/Update, ModelCategoryCreate/Update, SupportedModelCreate/Update, ModelCatalogOperationResponse | 217 (D-06 of Phase 4 already migrated reads, Phase 5 appends writes) |
| `api_service/schemas/admin/routing_setting.py` | RoutingSettingItem/Update/BatchUpdate/GroupResponse | 41 |
| `api_service/schemas/admin/route_monitor.py` | RouteRequestListItem/Detail/AggregateData/CompareItem | 137 |
| `api_service/schemas/admin/service_logs.py` | ServiceLogEntry/ServiceLogResult/ServiceLogsResponseData | 48 |
| `api_service/schemas/admin/user_management.py` | UserListItem/UserDetailData/AdjustUserBalanceRequest/UpdateUserRpmRequest/UserUsageAnalyticsData etc. | 275 |
| `api_service/schemas/admin/voucher.py` | GenerateVoucherCodesRequest/VoucherCodeItem/VoucherCodeCreateData | 80 |
| `api_service/core/policies.py` (EXTEND if exists from Phase 4) | Add `require_active_admin`, `require_super_admin` | ~30 |
| `api_service/main.py` (MODIFY) | Register `super_admin_bootstrap` lifespan hook | +10 lines |
| `api_service/core/router.py` (MODIFY) | `api_router.include_router(admin_router, prefix="/admin")` | +5 lines |

### Recommended Project Structure (after Phase 5)

```
api_service/
├── common/
│   ├── schemas.py            # NEW — D-04 hoist (ApiResponse[T], DateTimeModel, BaseResponse, ErrorResponse)
│   └── internal.py           # NEW — HMAC client ported from admin-service (see Pitfall 1)
├── controllers/
│   ├── admin/                # NEW directory — all admin endpoints
│   │   ├── __init__.py       # admin_router = APIRouter(); include_router for each
│   │   ├── auth.py
│   │   ├── admin_users.py
│   │   ├── audit_logs.py
│   │   ├── pools.py
│   │   ├── model_catalog.py
│   │   ├── routing_settings.py
│   │   ├── users.py          # user_management proxy elimination
│   │   ├── dashboard.py
│   │   ├── vouchers.py
│   │   ├── route_monitor.py
│   │   └── service_logs.py
│   └── (Phase 4 user-domain controllers — unchanged)
├── services/
│   ├── admin/                # NEW directory — admin services
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── bootstrap_service.py
│   │   ├── management_service.py
│   │   ├── audit_service.py
│   │   ├── pool_service.py
│   │   ├── model_catalog_service.py
│   │   ├── routing_setting_service.py
│   │   ├── health_check_service.py
│   │   ├── admin_user_service.py        # NEW (proxy elimination)
│   │   ├── dashboard_service.py         # NEW
│   │   ├── voucher_service.py           # NEW
│   │   ├── route_monitor_service.py     # NEW
│   │   └── service_logs_service.py      # NEW
│   └── (Phase 4 user-domain services — unchanged)
├── schemas/
│   ├── admin/                # NEW directory
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── admin_user.py
│   │   ├── audit_log.py
│   │   ├── pool.py
│   │   ├── model_catalog.py             # extends Phase 4 reads with writes
│   │   ├── routing_setting.py
│   │   ├── route_monitor.py
│   │   ├── service_logs.py
│   │   ├── user_management.py
│   │   └── voucher.py
│   └── common.py             # DELETE or empty shell after D-04 hoist
└── (Phase 1–4 baseline — DB, repos, models, common/security/utils — unchanged)
```

### Pattern 1: Admin Cookie Naming (Reproduce Source Verbatim)

**What:** Two cookies — `admin_access_token` (access) + `admin_refresh_token` (refresh). Path is `/` (NOT `/api/v1/admin`); cookie name is the namespacing axis. This matches the admin-service source explicit comment at `controllers/auth.py:38-41`:

```python
# Source: services/admin-service/src/controllers/auth.py:38-44 [VERIFIED]
ADMIN_ACCESS_COOKIE = "admin_access_token"
ADMIN_REFRESH_COOKIE = "admin_refresh_token"
ADMIN_COOKIE_PATH = "/"
```

The source comment explicitly states: *"The path stays at '/' because Next.js page-level middleware (which gates /login, /dashboard, etc.) needs to read the cookie before any /api request fires."*

**Note for CONTEXT.md "specifics" — `path` set to `/api/v1/admin`:** CONTEXT.md `<specifics>` suggests cookie path `/api/v1/admin`. **This contradicts the source's explicit operational requirement.** The Next.js admin frontend uses page-level middleware that runs *before* any API call, and that middleware reads the cookie via `document.cookie`. A cookie with `path=/api/v1/admin` won't be sent for `/` page navigation requests, so middleware redirects unauthenticated users — but the cookie *is present* and *is valid*, just unreadable in the path scope. **Preserve `path="/"` and rely on the cookie *name* (`admin_*`) to keep namespaces clean.** Adding `path=/api/v1/admin` would break the Next.js frontend on the very first deploy.

The planner should flag this as a discrepancy between CONTEXT.md `<specifics>` and source intent, and **default to source behavior** unless the user explicitly confirms the path change is desired. Confidence: HIGH that source is correct (source has a load-bearing comment); user's `<specifics>` may be over-eager scope tightening.

**Token blacklist (Phase 3 D-07):** Admin auth retains the JWT JTI blacklist via `common.security.token_blacklist`. Both access and refresh tokens are blacklisted on logout AND on change-password (with each token's remaining TTL).

### Pattern 2: Audit Log Explicit Write (D-02b)

**What:** Every admin mutation writes an audit row via `await AdminAuditService.record(...)` *before* `await db.commit()`. The audit row gets committed atomically with the mutation.

**Why explicit:** D-02b — no decorators, no middleware. Each mutation site is auditable in plain code review without indirection.

**Pattern (after porting source):**
```python
# Source pattern from routing_setting_service.py:84-99 [VERIFIED]
before_value = setting.value
await repo.update_value(key, value, updated_by=actor_admin_id)
await AdminAuditService.record(
    db,
    actor_admin_id=actor_admin_id,
    target_admin_id=None,
    action="update_routing_setting",
    resource_type="routing_setting",
    resource_id=key,
    status="success",
    before_data={"key": key, "value": before_value},
    after_data={"key": key, "value": value},
    ip_address=ip_address,
    user_agent=user_agent,
)
await db.commit()
```

**Failure handling (CONTEXT discretion):** Audit write failure should `logger.warning` + NOT raise. The mutation that already succeeded should commit. This is **opposite** to source's `safe_audit_commit` pattern (which rolls back the entire transaction on audit failure — see Pitfall 4). Planner must decide and document explicitly:

| Option | Behavior on audit failure | Used by |
|--------|---------------------------|---------|
| **A — Roll back** (source `safe_audit_commit` pattern) | The mutation reverts; user sees error | Current admin-service (8 controllers via `safe_audit_commit`) |
| **B — Commit anyway** (CONTEXT discretion) | The mutation succeeds; only audit row missing; log CRITICAL | Recommended by CONTEXT — minimizes business impact |

**Recommendation:** Adopt option B. Rationale: in the merged service, the audit table and the business table share the same SQLAlchemy session and same MySQL transaction — if the **commit itself** fails, both rows are lost together (transactional integrity preserved). The only way "audit fails but business commits" can occur is if `AdminAuditService.record` raises before the commit (e.g., bad enum value, missing column). In that case, the data the operator already changed in memory is reverted by the exception's rollback. **Option A and Option B converge in the merged architecture** as long as `AdminAuditService.record` runs *before* `db.commit()`. The wrapper helper `safe_audit_commit` was needed in the source because the gateway HTTP call had already mutated user-service state irreversibly. Post-merge this is no longer true.

**Concrete recommendation:** Drop `safe_audit_commit` entirely. Replace all 11 controller call sites with inline `await AdminAuditService.record(...)` + `await db.commit()`. Audit failures naturally trigger SQLAlchemy rollback. No need for option-A/B branching.

### Pattern 3: D-05 Cache Invalidation Hook

**What:** Every write method in `ModelCatalogService` ends with `await _invalidate_cache()` *after* `await db.commit()` (so we don't clear cache on rollback).

**Implementation:**
```python
# api_service/services/admin/model_catalog_service.py (NEW helper method)
from api_service.common.infra.cache import get_cache_redis

class ModelCatalogService:
    @staticmethod
    async def _invalidate_cache() -> None:
        """Invalidate all mc:* cache keys (D-05). Called after every successful write."""
        try:
            r = get_cache_redis()
            async for key in r.scan_iter(match="mc:*"):
                await r.delete(key)
        except Exception:
            # Fail-open — cache TTL (max 300s) will eventually expire stale entries
            logger.warning("model_catalog cache invalidation failed", exc_info=True)
```

**Wire into** every `create_vendor` / `update_vendor` / `delete_vendor` / `create_category` / `update_category` / `delete_category` / `create_model` / `update_model` / `disable_model` / `update_category_map` after `await db.commit()`.

**Why fail-open:** TTL upper bound = 300s. Worst case, stale data for 5 minutes — acceptable per CONTEXT D-05.

### Pattern 4: D-06 Routing Config Version Signal

**What:** Every write in `RoutingSettingService` ends with `await redis.incr("routing_config:version")` after `await db.commit()`.

**Implementation:**
```python
# api_service/services/admin/routing_setting_service.py (NEW hook)
from api_service.common.infra.cache import get_cache_redis

ROUTING_CONFIG_VERSION_KEY = "routing_config:version"

class RoutingSettingService:
    @staticmethod
    async def _bump_version() -> None:
        """Bump routing_config version (D-06). Phase 6 RoutingConfigCache polls this key."""
        try:
            r = get_cache_redis()
            await r.incr(ROUTING_CONFIG_VERSION_KEY)
        except Exception:
            # Fail-open — Phase 6 cache will eventually expire on its own TTL
            logger.warning("routing_config version bump failed", exc_info=True)
```

**Wire into** `update_setting` + `batch_update`. Phase 5 has no consumer; Phase 6 reads.

### Pattern 5: Bootstrap Lifespan Registration

**What:** `AdminBootstrapService.ensure_super_admin()` is called from a lifespan startup hook. The hook is idempotent and uses a MySQL `GET_LOCK` to prevent concurrent workers from double-creating.

**Implementation (target):**
```python
# api_service/main.py (MODIFY — append after database registration)
async def _bootstrap_super_admin() -> None:
    """Create super admin on first startup if BOOTSTRAP_SUPERADMIN_ENABLED."""
    from api_service.services.admin.bootstrap_service import AdminBootstrapService
    await AdminBootstrapService.ensure_super_admin()

# priority MUST be > 20 (DB) but < 100 (default).
# Recommend priority=25 — after DB (20), before Redis (30) is fine; before workers.
registry.register("super_admin_bootstrap", init_fn=_bootstrap_super_admin, priority=25)
```

**Priority discipline:**
- `logging` priority=0
- `snowflake` priority=10
- `database` priority=20
- `super_admin_bootstrap` priority=25  ← **NEW**
- `redis` priority=30
- `cache_redis` priority=30
- `arq_pool` priority=40 (Phase 4)

The bootstrap only needs the DB engine + session factory. Putting it at 25 ensures it runs *after* DB is up but doesn't block Redis (which is needed for the rest of the request lifecycle).

**Failure mode:** `AdminBootstrapService.ensure_super_admin` raises `RuntimeError` if `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True` and no super admin exists. This is intentional — admin-service refuses to start without a super admin. Preserve verbatim.

**MySQL GET_LOCK:** Uses `AdminUserRepository.acquire_named_lock("bootstrap_super_admin", 10)` already verified at `api_service/repositories/admin_user_repository.py:51-56`. The lock is connection-scoped — released on connection close. Source's pattern is idempotent: if lock acquisition fails, re-check the active super_admin count and bail if one exists.

### Pattern 6: Service Logs Aggregation (D-03)

**What:** Single endpoint `/api/v1/admin/service-logs` returns recent log entries from (1) local in-process RingBuffer and (2) inference-service via HMAC HTTP. Drop user-service and router-service from `_REMOTE_SERVICES`.

**Implementation skeleton:**
```python
# api_service/services/admin/service_logs_service.py (NEW)
import asyncio
import logging
from typing import Any

from api_service.common.internal import InternalServiceError, get_internal_json
from api_service.common.observability import get_ring_buffer
from api_service.core.config import settings

logger = logging.getLogger(__name__)
_LOG_FETCH_TIMEOUT = 3.0

# D-03: only inference remains
_REMOTE_SERVICES: list[tuple[str, str]] = [
    ("inference-service", "INFERENCE_SERVICE_URL"),
]

class AdminServiceLogsService:
    @staticmethod
    async def fetch_all(*, services=None, level=None, since=None, until=None,
                       search=None, after_seq=0, page=1, page_size=50):
        query_params: dict[str, Any] = {"page": page, "page_size": page_size}
        if level: query_params["level"] = level
        if since: query_params["since"] = since
        if until: query_params["until"] = until
        if search: query_params["search"] = search
        if after_seq: query_params["after_seq"] = after_seq

        targets = _resolve_targets(services)
        tasks = []
        for svc_name, base_url in targets:
            if svc_name == "api-service":  # local — was "admin-service" pre-merge
                tasks.append(_fetch_local(svc_name, query_params))
            else:
                tasks.append(_fetch_remote(svc_name, base_url, query_params))
        return await asyncio.gather(*tasks)


def _resolve_targets(services):
    all_targets = [("api-service", "")]
    for svc_name, url_attr in _REMOTE_SERVICES:
        all_targets.append((svc_name, getattr(settings, url_attr)))
    if not services:
        return all_targets
    requested = set(services)
    return [(n, u) for n, u in all_targets if n in requested]


async def _fetch_local(service, params):
    buf = get_ring_buffer()
    if buf is None:
        return _result(service, reachable=True, entries=[], total=0, latest_seq=0)
    entries, total, latest_seq = buf.snapshot(
        after_seq=params.get("after_seq", 0),
        level=params.get("level"), since=params.get("since"), until=params.get("until"),
        search=params.get("search"), page=params.get("page", 1), page_size=params.get("page_size", 50),
    )
    return _result(service, reachable=True, entries=entries, total=total, latest_seq=latest_seq)


async def _fetch_remote(service, base_url, params):
    try:
        payload = await get_internal_json(
            base_url=base_url, target_service=service,
            path="/api/v1/internal/logs",
            secret=settings.INTERNAL_SECRET,
            caller_service=settings.SERVICE_NAME,
            timeout=_LOG_FETCH_TIMEOUT,
            query_params=params,
            max_retries=0,
        )
        return _result(service, reachable=True,
                       entries=payload.get("entries", []),
                       total=payload.get("total", 0),
                       latest_seq=payload.get("latest_seq", 0))
    except InternalServiceError as exc:
        logger.warning("Failed to fetch logs from %s: %s", service, exc)
        return _result(service, reachable=False, error=str(exc))


def _result(service, *, reachable, entries=None, total=0, latest_seq=0, error=None):
    return {"service": service, "reachable": reachable,
            "entries": entries or [], "total": total,
            "latest_seq": latest_seq, "error": error}
```

**Pre-requisite:** `api_service/common/internal.py` (HMAC client) does not yet exist in api-service. See Pitfall 1.

### Anti-Patterns to Avoid

- **Adding `acting_admin_id` to Phase 4 user services** (D-02a forbids). Admin service is the boundary that knows *who* is acting.
- **Decorators or middleware for audit** (D-02b forbids). Explicit is mandatory.
- **Re-using `path="/api/v1/admin"` for the cookie.** Breaks Next.js admin frontend page middleware. Use `path="/"`.
- **Forgetting to invalidate `mc:*` after admin model_catalog write.** Users will see stale data up to 300s — but TTL is the safety net, so this is a quality bug, not a correctness bug.
- **Forgetting to INCR `routing_config:version` after admin routing_settings write.** Phase 6 cache won't refresh. Pure quality bug because Phase 6 isn't yet built; will surface in Phase 9 integration test.
- **Wiring bootstrap via cron / background task.** It's a startup-time concern; deferring to ARQ adds startup race (workers run before web process).
- **Cross-naming `AdminUserService`** (proxy-elimination for end-user management) **vs. `AdminManagementService`** (admin-on-admin CRUD). These are different! Recommend keeping `AdminManagementService` for admin-on-admin and renaming proxy-elimination service `AdminEndUserService` or `AdminUserOpsService`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HMAC-signed inter-service HTTP | Custom signature + retry + circuit breaker | Port `admin-service/src/common/internal.py` to `api_service/common/internal.py` | 552-line file with circuit breaker state, canonical request/body normalization, timestamp window — battle-tested in admin-service. Verbatim port plus import path rewrites |
| AES-256-GCM provider key encryption | Hand-roll cryptography | `api_service.common.security.crypto.{encrypt_api_key, decrypt_api_key, mask_api_key}` | Already in Phase 1 baseline |
| MySQL named lock for bootstrap | Redis SETNX | Use `AdminUserRepository.acquire_named_lock` (already present, MySQL `GET_LOCK`) | Atomicity with DB transaction; lock auto-released on connection close |
| Audit log generic envelope / category mapping | Custom dict logic | `AdminAuditCategory` Literal + `audit_action_definitions` table + module cache in `AdminAuditService` | Already designed; ports cleanly |
| Pagination response shape | Custom dict per controller | `PaginatedResponse[T]` from `api_service.common.api.pagination` | Verified in Phase 4 research |
| Cookie set/clear | Per-controller helpers | Single `_set_auth_cookies` / `_clear_auth_cookies` module-level helper in `controllers/admin/auth.py` | Source already has this; preserve |
| ApiResponse envelope | Custom dict returns | `ApiResponse[T]` from `api_service.common.schemas` (D-04 hoisted) | Phase 4 user-domain already uses; D-04 unifies for admin |
| Provider balance parsing | Per-provider parsing in controller | `PoolService._extract_balance(body) → int` (handles `total_remain`, `points`, `balance`, `remain` keys) | Source already covers 4 different provider response shapes |
| Health check rate limiting | Manual sleep + counter | `asyncio.Semaphore(HEALTH_CHECK_CONCURRENCY=5)` + `await asyncio.sleep(settings.HEALTH_CHECK_RATE_LIMIT_DELAY)` | Source pattern in `health_check_service.py` |
| Redis SCAN iteration | Manual `KEYS` + filter | `async for key in redis.scan_iter(match='mc:*')` | KEYS blocks Redis on large keyspaces; SCAN is non-blocking |
| Audit action label cache | New cache system | Module-level dict in `services/admin/audit_service.py` (`_action_defs_cache`, `_category_actions_cache`, `_action_labels_cache`) | Source pattern, invalidate on label update |

**Key insight:** Phase 5 is dominated by source ports. The new code surface is small: 5 proxy-elimination services + D-05 hook + D-06 hook + service_logs target swap. Resist the urge to "improve" anything during port.

## Runtime State Inventory

This phase is a 1:1 migration with proxy elimination. Code lives in a new directory tree but reads/writes the same database tables and Redis keys. The migration deletes 5 gateway modules but does not change schema.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None new. Phase 5 reuses `admin_users`, `admin_audit_logs`, `audit_action_definitions`, `pools`, `pool_accounts`, `pool_model_configs`, `model_catalog`, `model_vendor`, `model_category`, `model_catalog_category_map`, `routing_settings` — all present in Phase 3 baseline migration. Bootstrap upsert may write 1 super_admin row. | Schema unchanged. Bootstrap is idempotent. |
| Live service config | **`routing_config:version` Redis key (db/2)** — D-06 new. Phase 5 starts writing it; consumer (Phase 6) does not exist yet. Key has no TTL (intentional; INCR is safe across restarts). | Phase 5 plan must document the contract: type is integer, semantics is monotonic counter, key persists forever. |
| OS-registered state | The admin-service deployment registered an ARQ worker (cron jobs for health checks). Phase 5 ports `HealthCheckService` but **does NOT** add it to the api-service worker by default. **If health check cron is wanted in api-service, planner must add it to `api_service.core.jobs` (Phase 4 module) explicitly.** | Document as "deferred to deployment-time decision" in 05-02 plan; can also be a one-line addition in Wave 3. |
| Secrets/env vars | **NEW required on api-service:** `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP` (admin-service had default True; api-service config currently lacks this key), `BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS`, `BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS`, `HEALTH_CHECK_TIMEOUT_SECONDS`, `HEALTH_CHECK_LLM_PROBE_ENABLED`, `HEALTH_CHECK_LLM_PROBE_MAX_TOKENS`, `HEALTH_CHECK_RATE_LIMIT_DELAY`. **Already present on api-service:** `BOOTSTRAP_SUPERADMIN_ENABLED`, `BOOTSTRAP_SUPERADMIN_EMAIL`, `BOOTSTRAP_SUPERADMIN_PASSWORD`, `BOOTSTRAP_SUPERADMIN_NAME`, `PROVIDER_SECRET_MASTER_KEY`, `INFERENCE_SERVICE_URL`, `INFERENCE_SERVICE_SECRET`, `INTERNAL_SECRET`, `SERVICE_NAME`. **Deleted (no longer needed):** `USER_SERVICE_URL`, `ROUTER_SERVICE_URL` — formerly used by admin-service gateways; api-service config currently doesn't have these either (verified `core/config.py` doesn't declare them). | Add 7 new keys to `ApiServiceSettings`. Document each default in the Settings Gap table below. |
| Build artifacts | None. `pip install -e .` already covers all admin code. | None. |

**Settings Gap (must add to `ApiServiceSettings` in 05-01 Wave 0 alongside D-04 hoist):**

| Setting | Default | Source line |
|---------|---------|-------------|
| `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP` | True | `admin-service/src/core/config.py:76` |
| `BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS` | False | `admin-service/src/core/config.py:80` |
| `BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS` | False | `admin-service/src/core/config.py:81` |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | 15.0 | `admin-service/src/core/config.py:88` |
| `HEALTH_CHECK_LLM_PROBE_ENABLED` | True | `admin-service/src/core/config.py:89` |
| `HEALTH_CHECK_LLM_PROBE_MAX_TOKENS` | 5 | `admin-service/src/core/config.py:90` |
| `HEALTH_CHECK_RATE_LIMIT_DELAY` | 0.5 | `admin-service/src/core/config.py:91` |
| `INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD` | 5 | admin-service (referenced in `service_logs.py:90`) |
| `INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | 30 | admin-service (referenced in `service_logs.py:91`) |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MySQL 8.0 (with `GET_LOCK` support) | Bootstrap exclusion | ✓ (Phase 2) | 8.0.x | — |
| Redis db/2 with `SCAN MATCH` + `INCR` | D-05, D-06 | ✓ (Phase 2) | 5.x | — |
| Local RingBuffer | D-03 | ✓ (Phase 1 — `common/observability.py:97`) | — | — |
| HMAC client (`get_internal_client` / `get_internal_json`) | D-03 inference HTTP | **✗ NOT YET PRESENT** in api-service. Admin-service has it (`common/internal.py`, 552 lines). | — | **Port from admin-service before D-03 can land.** See Pitfall 1. |
| inference-service `/api/v1/internal/logs` endpoint | D-03 remote fetch | Existing on inference-service today (admin-service queries it via gateway) | — | partial result + warning if unreachable (preserve degradation) |
| `cryptography` (AES-GCM) | Pool account encryption | ✓ (Phase 4 baseline pyproject) | >=42.0 | — |
| `httpx` (async) | HMAC client + upstream balance checks | ✓ (Phase 4 baseline) | >=0.26 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- **`api_service.common.internal` module** — must be ported from admin-service in 05-01. Without it, `AdminServiceLogsService._fetch_remote` cannot be implemented; alternatives are inline HMAC building (50+ lines per call site, undesirable) or just-local-RingBuffer mode (drops inference-service log visibility — acceptable degradation but loses functionality). **Recommend port.**

## Common Pitfalls

### Pitfall 1: api-service is missing `common/internal.py` — HMAC client
**What goes wrong:** `AdminServiceLogsService` (D-03) imports `from api_service.common.internal import get_internal_json, InternalServiceError`. This module **does not exist** in api-service today. Phase 1 split internal HMAC into `common/http/internal_auth.py` (receiver side only — verified). The sender side (`get_internal_client`, `get_internal_json`, `request_internal_json`, circuit breaker) lives only in admin-service `common/internal.py`.
**Why it happens:** Phase 1 D-04 deliberately deferred the sender side to "Phase 6 when InferenceClient lands". Phase 5 actually needs the sender side first (for D-03 service logs aggregation).
**How to avoid:** Plan 05-01 (or a Wave 0 task inside it) must port `admin-service/src/common/internal.py` → `api_service/common/internal.py`. The receiver-side `build_internal_auth_dependency` already exists in api-service `common/http/internal_auth.py` (verified) — the planner must dedupe carefully so we don't have two implementations of `_canonicalize_request_body` / `_build_internal_signature`.
**Recommendation:** Refactor as you port. Move all signature primitives (`_canonicalize_request_body`, `_canonicalize_request_query`, `_canonicalize_request_target`, `_build_internal_signature`) to a single module (e.g., `api_service/common/http/internal_signing.py`). Then `common/internal.py` (sender) and `common/http/internal_auth.py` (receiver) both import from it. Net result: zero duplication, two clear modules.
**Warning signs:** `ImportError: cannot import name 'get_internal_json' from 'api_service.common.internal'` at first run of `AdminServiceLogsService`.

### Pitfall 2: `safe_audit_commit` semantics differ in merged service
**What goes wrong:** Source uses `from utils.audit import safe_audit_commit` in 11+ controller files. The helper wraps audit write in `try/except → rollback on failure`. In the merged service, this rollback would also revert the business mutation — which is the **opposite** of what CONTEXT discretion suggests ("log warning, don't throw / block business mutation").
**Why it happens:** In the source, the gateway HTTP call had already irreversibly mutated user-service state when audit ran. Rolling back the admin-side audit row left the user-side change orphaned. Post-merge, audit row + business row share the transaction — rollback is safe AND the desired behavior.
**How to avoid:** Drop `safe_audit_commit` entirely. Replace 14 call sites with explicit `await AdminAuditService.record(...) + await db.commit()`. Any audit failure naturally aborts the whole transaction (including the business mutation) and surfaces as a 500 response. This is correct.
**Warning signs:** Tests passing locally but production reports "operation succeeded but audit log missing" — happens when planner mistakenly keeps `safe_audit_commit` wrapper.

### Pitfall 3: Naming collision — `AdminUserService` (proxy) vs `AdminManagementService` (admin-on-admin)
**What goes wrong:** CONTEXT D-02 names the proxy-elimination service `admin_user_service.py` (managing END users from admin perspective). Source already has `management_service.py` containing `AdminManagementService` (admin-on-admin CRUD). Both will live in `services/admin/`. Tests, IDE auto-imports, and code reviews will conflate them.
**Why it happens:** Domain language is genuinely overloaded — "admin user" can mean "the user being administered" or "the admin's account itself."
**How to avoid:** Rename one. Recommendation:
- `services/admin/management_service.py` → `AdminAccountService` (manages **admin accounts**)
- `services/admin/admin_user_service.py` → keep name (manages **end users** from admin perspective) OR rename to `AdminEndUserService` / `AdminUserOpsService`
**Recommendation:** Rename source `AdminManagementService` → `AdminAccountService`. This is a one-time refactor with clear intent. Document in 05-01 plan as `D-discretion-1`.
**Warning signs:** Reviewer asks "which one of these do I look at?"

### Pitfall 4: `routing_setting_service.resolve_for_internal()` is OUT OF SCOPE
**What goes wrong:** Source `routing_setting_service.py:186-240` has `resolve_for_internal(db)` that assembles the full routing config payload for inference-service consumption (via the soon-deleted `/api/v1/internal/routing-config/active/*` endpoint).
**Why it happens:** This method exists only to serve the internal endpoints in `controllers/internal.py` which D-01b **does NOT migrate** (Phase 8 may rebuild). So `resolve_for_internal` has zero callers post-migration.
**How to avoid:** **Do NOT port `resolve_for_internal`.** Port lines 1-185 of `routing_setting_service.py` only. Note this as a deliberate scope cut in 05-02. Phase 8 can re-port it if/when the internal endpoints are rebuilt.
**Warning signs:** Planner ports entire file and we end up with dead code that will confuse future readers.

### Pitfall 5: `model_catalog.py` PUBLIC controller (96 lines) is NOT migrated
**What goes wrong:** admin-service has two controllers with similar names: `controllers/model_catalog_admin.py` (261 lines, admin write CRUD — **MIGRATE**) and `controllers/model_catalog.py` (96 lines, **PUBLIC** read endpoints `/models` `/model-vendors` etc — **DO NOT MIGRATE**, Phase 4 D-06 already handles).
**Why it happens:** Sources have non-prefixed paths; admin-service mounts both with a single `/admin` router (the public one was probably an early mistake never cleaned up).
**How to avoid:** Plan 05-02 explicitly excludes `admin-service/src/controllers/model_catalog.py`. The corresponding service methods (`ModelCatalogService.list_vendors` / `list_categories` / `list_models` etc.) ARE ported because admin write controllers use them — but the Phase 4 D-06/D-07 user-domain `ModelCatalogReadService` also exists. Two services touching the same repo is fine; they just expose different filter defaults (`active_only=True` for users, `active_only=False` for admin list).
**Warning signs:** Double-mounted `/models` route → FastAPI raises duplicate-path error on startup, OR worse, silent path shadowing.

### Pitfall 6: Bootstrap requires DB engine + session factory — register AFTER `database`
**What goes wrong:** If `super_admin_bootstrap` lifespan hook runs before `database`, `AdminUserRepository.acquire_named_lock` calls fail with "engine not initialised".
**Why it happens:** Lifespan registry sorts ascending priority. Default priority is 100. If planner registers bootstrap with no priority, it runs at 100 — after DB (20). That's actually fine. But if planner mistakenly sets it to 5 thinking "early init", it crashes.
**How to avoid:** Priority = 25 (after DB at 20, before Redis at 30). Document in `main.py` comment.
**Warning signs:** Startup logs show `resource_init_failed extra={resource:'super_admin_bootstrap'}` with stack pointing at `init_session_factory not called`.

### Pitfall 7: Phase 4 schema imports must be rewritten in 05-01
**What goes wrong:** After D-04 hoist, every Phase 4 file containing `from api_service.schemas.common import ApiResponse, DateTimeModel, AuthBaseResponse` breaks. D-04 says rewrite imports in Phase 5 plan 05-01.
**Why it happens:** D-04 was the deferred Phase 4 D-03 question; we're paying the debt now.
**How to avoid:** Plan 05-01 first task is a `grep -rln "api_service.schemas.common" services/api-service/` audit. Every match is rewritten in the same commit as the new `common/schemas.py` file. Pre-merged check: imports refer to `from api_service.common.schemas import ApiResponse, DateTimeModel, BaseResponse`.
**Warning signs:** Phase 4 tests pass before Phase 5 lands; after the D-04 commit they fail with `ImportError: cannot import name 'AuthBaseResponse'`.
**Affected files (Phase 4 plans 04-01 / 04-02 / 04-03 will have written, NOT yet present today):**
- `api_service/schemas/auth.py` (Phase 4 04-01)
- `api_service/schemas/keys.py` (Phase 4 04-02)
- `api_service/schemas/billing.py` (Phase 4 04-02)
- `api_service/schemas/model_catalog.py` (Phase 4 04-03 — read schemas only)
- `api_service/schemas/__init__.py` (Phase 4 04-01)
- All controllers/services that import from `schemas.common`

### Pitfall 8: `AdminBaseResponse` → `BaseResponse` semantic merge
**What goes wrong:** Source admin-service `AdminBaseResponse` has `code=200, message="success"`; user-service `AuthBaseResponse` has the same fields and defaults — they're behaviorally identical, ONLY name differs. After D-04 the unified class is `BaseResponse(code, message)`. Phase 5 admin schemas currently extend `AdminBaseResponse`; Phase 4 user schemas (if already written) extend `AuthBaseResponse`. Both need to become `BaseResponse`.
**Why it happens:** Pure naming cleanup.
**How to avoid:** D-04 hoist writes `BaseResponse` (not `AuthBaseResponse` or `AdminBaseResponse`). Plan 05-01 immediately after hoist:
1. `sed -i 's/AuthBaseResponse/BaseResponse/g'` for user-domain files
2. `sed -i 's/AdminBaseResponse/BaseResponse/g'` for admin-domain files being ported
3. Keep `AuthErrorResponse` / `AdminErrorResponse` collapsed into single `ErrorResponse` (default `code=400`).
**Warning signs:** Two `BaseResponse` classes inadvertently created (one in `common/schemas.py`, one shadow in `schemas/admin/common.py`).

### Pitfall 9: Pool service `_extract_balance` is provider-specific
**What goes wrong:** `_extract_balance` handles 4 provider response shapes (`total_remain`, `points`, `balance`, `remain` — verified at `services/admin-service/src/services/pool_service.py:90-100`). Porting changes risk dropping support for one shape silently. Tests for this don't exist in source.
**Why it happens:** Source accumulated provider-specific handling over time without tests.
**How to avoid:** Port verbatim. Add **at least one unit test per supported shape** in Wave 0 of 05-02. Use a parameterized pytest fixture with 4 representative response bodies.
**Warning signs:** A provider switch (deeplink → new vendor) silently sets balance to 0 because their response uses an undocumented key.

### Pitfall 10: HealthCheckService cron registration is undefined
**What goes wrong:** Source admin-service registers health-check as an ARQ cron in `services/admin-service/src/core/jobs.py`. Phase 5 ports the service module but not the cron registration. If the planner forgets to add it to api-service's `core/jobs.py`, channel balance probing stops happening — silently.
**Why it happens:** D-07 plan split doesn't explicitly mention cron registration; bootstrap_service is named but health_check is just "migrate".
**How to avoid:** Plan 05-02 last task: "register `run_health_checks` as ARQ cron in `api_service/core/jobs.py`, schedule = `cron(hour={3}, minute={0})` or every-6h depending on source frequency." Document the chosen schedule.
**Recommendation:** Default to source's cadence. If source uses `cron(hour=*, minute=*/30)` (every 30 min), preserve that.
**Warning signs:** Channels show stale `last_checked_at` in admin UI after 24h of running new service.

### Pitfall 11: Admin service uses `from common.token_blacklist` not `from common.security.token_blacklist`
**What goes wrong:** Admin-service `auth_service.py:23` imports `from common.token_blacklist import blacklist_token, is_token_blacklisted`. Phase 1 D-02 moved this to `api_service.common.security.token_blacklist` (verified at `api_service/common/security/token_blacklist.py`). Import rewrite required.
**Why it happens:** Standard Phase 1 reorganization, same drift as Phase 4 Pitfall 2.
**How to avoid:** Import translation in 05-01: `from common.token_blacklist` → `from api_service.common.security.token_blacklist`.
**Warning signs:** `ModuleNotFoundError: No module named 'common.token_blacklist'` at first import of `AdminAuthService`.

### Pitfall 12: `core.dependencies.get_db_session` → `core.db.get_db`
**What goes wrong:** Same drift as Phase 4 Pitfall 3. Source admin uses `from core.dependencies import get_db_session, get_request_meta`. Phase 2 renamed to `get_db` in api-service.
**Why it happens:** Phase 2 scaffolding consolidation.
**How to avoid:** Replace `from core.dependencies import get_db_session, get_request_meta` with two separate imports:
- `from api_service.core.db import get_db`
- `from api_service.core.dependencies.admin import get_request_meta` (already verified at `api_service/core/dependencies/admin.py:94-98`)
**Warning signs:** Same as Phase 4 Pitfall 3.

### Pitfall 13: `from utils.audit import safe_audit_commit` does not move
**What goes wrong:** Admin-service `utils/audit.py` exists in source. Port would normally place it at `api_service/common/utils/audit.py`. But per Pitfall 2 we **delete this helper entirely** — its semantics are wrong for the merged service.
**Why it happens:** The helper is a code-smell artifact of the pre-merge HTTP-gateway architecture. Post-merge it should not exist.
**How to avoid:** Do NOT port `utils/audit.py`. Plan 05-03 (proxy elimination) deletes the imports. The 14 call sites become inline `await AdminAuditService.record(...) + await db.commit()`.
**Warning signs:** `api_service/common/utils/audit.py` exists at end of Phase 5 — that's a defect.

### Pitfall 14: `from core.policies import require_active_admin, require_super_admin`
**What goes wrong:** Phase 4 plan 04-01 RESEARCH proposes creating `api_service/core/policies.py` with `require_active_user`. Phase 5 needs `require_active_admin` + `require_super_admin` in the same file. Both must coexist.
**Why it happens:** Both domains have "active user / admin" guards but with different status enum values.
**How to avoid:** Plan 05-01 extends `core/policies.py` with two admin guards (verbatim from `admin-service/src/core/policies.py`):
```python
async def require_active_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.status != AdminStatus.ACTIVE:
        raise AdminPermissionDeniedException("Admin account inactive")
    return admin

async def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.role != AdminRole.SUPER_ADMIN:
        raise AdminPermissionDeniedException("Super admin permission required")
    return admin
```
**Warning signs:** `ImportError: cannot import name 'require_super_admin'` in admin controllers.

### Pitfall 15: `from core.exceptions import AdminConflictException, AdminPermissionDeniedException`
**What goes wrong:** admin-service has its own `core/exceptions.py` with `AdminConflictException` and `AdminPermissionDeniedException` (admin-specific). api-service `common/core/exceptions.py` doesn't include them.
**Why it happens:** Pre-merge, admin had its own subclass tree.
**How to avoid:** Plan 05-01 adds the two classes to `api_service.common.core.exceptions` (mapped to HTTP 409 and 403 respectively). Or — alternative — keep them in `api_service/core/exceptions.py` admin-specific module. Recommendation: put them in `common.core.exceptions` for consistency with `EmailAlreadyExistsException` and friends.
**Warning signs:** Two import paths for the same exception name during port.

## Code Examples

### Admin login (verified port)

```python
# Source: services/admin-service/src/controllers/auth.py:73-113 [VERIFIED]
# Target with translations applied:
from api_service.core.db import get_db                     # was core.dependencies.get_db_session
from api_service.core.policies import require_active_admin
from api_service.services.admin.auth_service import AdminAuthService
from api_service.common.security.jwt import create_refresh_token  # was common.utils.jwt
from api_service.common.schemas import BaseResponse        # D-04 hoisted (was schemas.common.AdminBaseResponse)
from api_service.schemas.admin.auth import (
    AdminLoginRequest, AdminLoginResponse, AdminLoginResponseData, AdminUserData,
)

router = APIRouter(prefix="/auth", tags=["admin-auth"])


@router.post("/login", response_model=AdminLoginResponse)
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminLoginResponse:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    admin, access_token = await AdminAuthService.login(
        db, payload.email, payload.password, user_agent, ip_address,
    )
    refresh_token = create_refresh_token(
        data={"uid": admin.uid, "sub": str(admin.uid)},
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )
    _set_auth_cookies(response, access_token, refresh_token)
    return AdminLoginResponse(
        code=200, message="登录成功",
        data=AdminLoginResponseData(
            user=AdminUserData(
                uid=str(admin.uid), email=admin.email, name=admin.name,
                role=admin.role, is_root=getattr(admin, "is_root", False),
            ),
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )
```

### Admin mutation with audit (post-Pitfall-2 simplification)

```python
# Replaces source's safe_audit_commit pattern (Pitfall 2)
# Target:
@router.post("/{uid}/topup", response_model=BaseResponse)
async def topup_user(
    uid: str,
    payload: TopupUserRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseResponse:
    ip_address, user_agent = get_request_meta(request)
    result = await AdminEndUserService.topup_user(
        db, target_uid=uid, amount=payload.amount,
        operator_admin=current_admin, remark=payload.remark,
    )
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="topup_user",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        after_data={"amount": payload.amount, "order_no": result.order_no},
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    return BaseResponse(message="充值成功")
```

### Bootstrap lifespan registration

```python
# api_service/main.py — add after database registration (priority=25)
async def _bootstrap_super_admin() -> None:
    from api_service.services.admin.bootstrap_service import AdminBootstrapService
    await AdminBootstrapService.ensure_super_admin()


registry.register(
    "super_admin_bootstrap",
    init_fn=_bootstrap_super_admin,
    priority=25,  # After database (20), before redis/cache_redis (30)
)
```

### D-05 cache invalidation in `ModelCatalogService`

```python
# Source: admin-service does NOT do this today — D-05 is NEW behavior
# Target:
from api_service.common.infra.cache import get_cache_redis

class ModelCatalogService:
    @staticmethod
    async def _invalidate_cache() -> None:
        try:
            r = get_cache_redis()
            async for key in r.scan_iter(match="mc:*"):
                await r.delete(key)
        except Exception:
            logger.warning("mc_cache_invalidate_failed", exc_info=True)

    @staticmethod
    async def create_vendor(db, payload, *, actor_admin_id, ip_address, user_agent):
        # ... existing port logic — repo.add(), commit, audit ...
        await db.commit()
        await ModelCatalogService._invalidate_cache()   # NEW per D-05
        return ModelCatalogService._vendor_item(vendor)
```

### D-06 routing config version bump

```python
# Target — append after every existing await db.commit() in routing_setting_service
from api_service.common.infra.cache import get_cache_redis

ROUTING_CONFIG_VERSION_KEY = "routing_config:version"

@staticmethod
async def update_setting(db, key, value, *, actor_admin_id, ip_address, user_agent):
    # ... existing port ...
    await db.commit()
    try:
        await get_cache_redis().incr(ROUTING_CONFIG_VERSION_KEY)
    except Exception:
        logger.warning("routing_config_version_bump_failed", exc_info=True)
    updated = await repo.get_by_key(key)
    return _setting_item(updated)
```

## State of the Art

| Old Approach (admin-service) | Current Approach (api-service Phase 5) | When Changed | Impact |
|------------------------------|---------------------------------------|--------------|--------|
| 5 HTTP gateways (user-mgmt / user-stats / route-monitor / service-logs / vouchers) | Direct service calls (D-02) | Phase 5 (2026-05-19) | Removes 4 network hops on every admin operation; deletes ~1000 lines of gateway boilerplate |
| `safe_audit_commit` (HTTP gateway era) | Explicit `await AdminAuditService.record(...) + await db.commit()` | Phase 5 (Pitfall 2) | Cleaner transaction semantics; one fewer abstraction |
| `AdminBaseResponse` vs `AuthBaseResponse` (split) | Unified `BaseResponse` in `common/schemas.py` (D-04) | Phase 5 (resolving Phase 4 D-03) | One canonical envelope class for the merged service |
| `schemas/common.py` duplicated user vs admin | Single `common/schemas.py` (D-04) | Phase 5 | Two near-identical files dedupe to one |
| `mc:*` Redis cache only TTL invalidation | `mc:*` SCAN+DEL on admin write (D-05) | Phase 5 | Admin changes visible immediately (vs up to 300s lag) |
| Admin writes routing settings → router-service polls user-service `/internal/system-settings` | Admin writes → INCR `routing_config:version` Redis key → Phase 6 RoutingConfigCache polls (D-06) | Phase 5 | Internal HTTP route deprecated |
| Per-call HMAC re-implementation per gateway | Shared `common/internal.py` with circuit breaker (port from admin-service) | Phase 5 (Pitfall 1) | One canonical HMAC sender |
| `controllers/internal.py` (HMAC-protected admin endpoints) | NOT MIGRATED (D-01b — Phase 8 rebuilds if needed) | Phase 5 | Drops 262 lines of code; relies on inference-service being adjusted in Phase 8 |
| user_management.py uses gateway path `/api/v1/internal/users/*` | Replaced with direct Python `await BalanceService.topup(...)` etc | Phase 5 | One source of truth for the operation |

**Deprecated/outdated for Phase 5:**
- `services/admin-service/src/gateways/` directory — **entirely deleted** post-Phase 5 (5 gateway files)
- `services/admin-service/src/utils/audit.py` — deleted (Pitfall 13)
- `services/admin-service/src/controllers/internal.py` — explicitly excluded by D-01b
- `services/admin-service/src/controllers/model_catalog.py` — explicitly excluded by D-01a (Phase 4 covers)
- `services/admin-service/src/services/routing_setting_service.py:186-240` (`resolve_for_internal`) — out of scope per Pitfall 4

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Cookie path should stay `/` (not `/api/v1/admin`) — source operational comment is authoritative | Pattern 1 | Wrong → Next.js admin frontend middleware can't read cookie → infinite login loop; first deploy breaks | `[VERIFIED via source comment]` |
| A2 | `safe_audit_commit` semantics should change to inline audit+commit (option B per Pitfall 2) | Pitfall 2 | If wrong → "audit succeeded but business reverted" or vice versa. Recommendation merges both into transactional safety. | `[ASSUMED — based on architectural reasoning]` |
| A3 | `routing_setting_service.resolve_for_internal()` has no Phase 5 caller and should be excluded | Pitfall 4 | If wrong (e.g., user-domain or relay needs default user RPM read from this) → import error. Source confirms callers are only the deleted internal endpoints. | `[VERIFIED — grep of admin-service]` |
| A4 | `HealthCheckService` cron registration is a Phase 5 deliverable, not Phase 9 | Pitfall 10 | If deferred to Phase 9, channels appear "stale" in admin UI but routing still works (balance is best-effort). Acceptable downgrade. | `[ASSUMED — deployment timing]` |
| A5 | `AdminManagementService` rename to `AdminAccountService` is non-breaking refactor | Pitfall 3 | One-time rename. Phase 5 controllers import the new name; no other phase depends on the old name. | `[VERIFIED — grep across all services]` |
| A6 | Phase 4 will be complete before Phase 5 plans 05-02/05-03 start | Summary | If Phase 4 is delayed, 05-03 cannot wire admin-end-user proxy services. Plans run in parallel per ROADMAP — but 05-03 depends on Phase 4 user services existing. | `[ASSUMED — coordinated execution]` |
| A7 | Admin frontend can absorb `/api/v1/admin/*` path prefix change (D-01) in one coordinated deploy | D-01c | If admin frontend can't update API_URL before backend cutover → admin UI breaks. CONTEXT D-01c flags this. | `[ASSUMED — coordinated deploy]` |
| A8 | `resolve_for_internal`'s `default_user_rpm` reader is duplicated by Phase 4 D-09 (`settings.DEFAULT_USER_RPM`) | Pitfall 4 | If user-domain still needs the DB-backed dynamic default, Phase 5 is the natural place to give it a DB read. Currently CONTEXT defers this entirely to Phase 5 future work. | `[VERIFIED in Phase 4 RESEARCH O-1]` |

**Items requiring user confirmation in discuss-phase before plan generation:**
- A1 (cookie path) — directly contradicts CONTEXT `<specifics>` line; planner needs explicit confirmation. **Recommended action:** ask user to confirm "keep path=/ per source operational comment" before plan 05-01 fixes cookie helpers.
- A2 (audit semantics simplification) — drops the `safe_audit_commit` helper entirely; ask user to confirm intent.
- A3 (drop `resolve_for_internal`) — confirms scope cut; low-risk but worth surfacing.
- A6 (Phase 4 dependency) — coordination question for execution ordering.

## Open Questions (RESOLVED)

> **All 5 questions resolved 2026-05-19 by user decision in /gsd:plan-phase plan-check loop.** CONTEXT.md D-08 locks O-1. O-2/O-3/O-4 deferred to in-plan read-source tasks. O-5 documented in plan metadata.

1. **O-1: Cookie path `/` vs `/api/v1/admin`** — **RESOLVED: `path="/"`** (locked as CONTEXT D-08)
   - What we know: Source uses `path="/"` with an explicit comment that Next.js middleware needs to read it. CONTEXT `<specifics>` suggests `path=/api/v1/admin`.
   - What's unclear: Did the user write `<specifics>` thinking about cookie security, unaware of the Next.js middleware requirement? Or has the admin frontend changed?
   - Recommendation: Default to source `path="/"`. Flag in plan-check for explicit user confirmation.

2. **O-2: `HealthCheckService` cron schedule** — **RESOLVED: read source in Plan 05-02 first task**
   - What we know: Source registers it via ARQ cron in admin-service `core/jobs.py`. Source file not yet inspected for exact schedule.
   - What's unclear: Every 30 min? Every 6 h? Tied to settings?
   - Recommendation: Read source `services/admin-service/src/core/jobs.py` during 05-02 planning and port verbatim. If source uses a settings key (likely `HEALTH_CHECK_CRON_SCHEDULE` or similar), add it to api-service settings.

3. **O-3: `inference-service` `/api/v1/internal/logs` endpoint path** — **RESOLVED: grep inference-service codebase in Plan 05-03 service_logs task**
   - What we know: admin-service gateway calls `/internal/logs` (no `/api/v1` prefix — source `service_logs.py:83`). The endpoint in inference-service likely lives at `/api/v1/internal/logs` based on inference-service conventions, but source uses just `/internal/logs`.
   - What's unclear: Which path does inference-service actually serve today?
   - Recommendation: Plan 05-03 task: verify `inference-service` log endpoint path by grepping its codebase (or via README). If `/internal/logs` is correct, preserve. If it's `/api/v1/internal/logs`, port with new path.

4. **O-4: `AdminAuditCategory` Literal definition order** — **RESOLVED: read source `schemas/audit_log.py` in Plan 05-02 audit task**
   - What we know: Source `schemas/audit_log.py:13` defines `AdminAuditCategory = Literal["all", ...other categories...]`. The "..." is unverified.
   - What's unclear: Full Literal set hasn't been read; planner must read this exhaustively before porting.
   - Recommendation: Plan 05-02 first-task includes a `Read` of `services/admin-service/src/schemas/audit_log.py` to capture the exact Literal members.

5. **O-5: ARQ worker registration for health check post-merge** — **RESOLVED: single worker (Phase 4's ARQ worker) per planner recommendation, documented in plan metadata**
   - What we know: Phase 4's `api_service/core/jobs.py` registers 4 user-domain cron jobs. Phase 5 needs to add `run_health_checks`. Source admin-service had a separate ARQ worker process — Phase 5 must decide: do health checks run in the same ARQ worker as Phase 4's user-domain jobs, or do they need a separate worker?
   - Recommendation: Single worker. Health check is async, semaphore-limited (concurrency=5), and runs once every N hours. Adding it to the user-domain ARQ worker has zero hot-path impact. Plan 05-02 last task: append `run_health_checks` to `api_service/core/jobs.py:WorkerSettings.functions` and add a `cron(...)` entry to `WorkerSettings.cron_jobs`.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23+ `[VERIFIED: Phase 4 RESEARCH.md]` |
| Config file | (none yet — Phase 4 04-01 creates `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`) |
| Quick run command | `cd services/api-service && pytest tests/ -x -q -k admin` |
| Full suite command | `cd services/api-service && pytest tests/ --cov=api_service --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADMIN-01 | Admin login sets `admin_access_token` cookie | integration | `pytest tests/test_admin_auth.py::test_login_sets_cookies -x` | ❌ Wave 0 |
| ADMIN-01 | Admin login locks account after 5 fails (`login_locked_until` set) | integration | `pytest tests/test_admin_auth.py::test_lockout -x` | ❌ Wave 0 |
| ADMIN-01 | Admin logout blacklists JTI | integration | `pytest tests/test_admin_auth.py::test_logout_blacklists -x` | ❌ Wave 0 |
| ADMIN-01 | Admin refresh rotates both tokens | integration | `pytest tests/test_admin_auth.py::test_refresh_rotates -x` | ❌ Wave 0 |
| ADMIN-01 | Admin change-password invalidates current tokens | integration | `pytest tests/test_admin_auth.py::test_change_password_invalidates -x` | ❌ Wave 0 |
| ADMIN-03 | `/api/v1/admin/users` lists users (no HTTP call) | integration | `pytest tests/test_admin_users.py::test_list_no_http -x` | ❌ Wave 0 |
| ADMIN-03 | Admin topup writes audit row + balance row in same transaction | integration | `pytest tests/test_admin_users.py::test_topup_atomic_with_audit -x` | ❌ Wave 0 |
| ADMIN-03 | Admin reset-password locks all user sessions | integration | `pytest tests/test_admin_users.py::test_reset_password_revokes_sessions -x` | ❌ Wave 0 |
| ADMIN-04 | Pool create writes encrypted `api_key_enc` (no plaintext) | integration | `pytest tests/test_admin_pools.py::test_create_encrypts_key -x` | ❌ Wave 0 |
| ADMIN-04 | Pool model add updates `pool_model_configs` | integration | `pytest tests/test_admin_pools.py::test_add_model -x` | ❌ Wave 0 |
| ADMIN-04 | Pool balance check decrypts + calls upstream | integration | `pytest tests/test_admin_pools.py::test_check_balances -x` | ❌ Wave 0 |
| ADMIN-05 | Model vendor create invalidates `mc:*` cache (D-05) | integration | `pytest tests/test_admin_model_catalog.py::test_create_vendor_invalidates_cache -x` | ❌ Wave 0 |
| ADMIN-05 | Model archive sets `is_active=False` (soft delete) | unit | `pytest tests/test_model_catalog_service.py::test_archive_soft_deletes -x` | ❌ Wave 0 |
| ADMIN-06 | Routing setting update bumps `routing_config:version` (D-06) | integration | `pytest tests/test_admin_routing_settings.py::test_update_bumps_version -x` | ❌ Wave 0 |
| ADMIN-06 | Tier model validation rejects missing pool coverage | unit | `pytest tests/test_routing_setting_service.py::test_validate_rejects_unavailable -x` | ❌ Wave 0 |
| ADMIN-07 | Dashboard summary returns int fields from direct repo call | integration | `pytest tests/test_admin_dashboard.py::test_summary_no_http -x` | ❌ Wave 0 |
| ADMIN-07 | Dashboard rpm-trend respects `bucket_seconds` | integration | `pytest tests/test_admin_dashboard.py::test_rpm_trend_bucketing -x` | ❌ Wave 0 |
| ADMIN-08 | Audit log meta returns categories + action_labels | integration | `pytest tests/test_admin_audit.py::test_meta -x` | ❌ Wave 0 |
| ADMIN-08 | Audit log list filters by category + actor_uid | integration | `pytest tests/test_admin_audit.py::test_list_filters -x` | ❌ Wave 0 |
| ADMIN-08 | Action label update invalidates module cache | unit | `pytest tests/test_audit_service.py::test_update_label_invalidates_cache -x` | ❌ Wave 0 |
| ADMIN-09 | Voucher generate batch writes N codes + 1 audit row | integration | `pytest tests/test_admin_vouchers.py::test_generate_batch -x` | ❌ Wave 0 |
| ADMIN-09 | Voucher disable sets status to inactive | integration | `pytest tests/test_admin_vouchers.py::test_disable -x` | ❌ Wave 0 |
| ADMIN-10 | Route monitor list paginates from `call_logs` | integration | `pytest tests/test_admin_route_monitor.py::test_list -x` | ❌ Wave 0 |
| ADMIN-10 | Route monitor compare returns siblings by input_hash | integration | `pytest tests/test_admin_route_monitor.py::test_compare -x` | ❌ Wave 0 |
| ADMIN-11 | Service logs returns local RingBuffer entries | integration | `pytest tests/test_admin_service_logs.py::test_local_only -x` | ❌ Wave 0 |
| ADMIN-11 | Service logs degrades gracefully when inference unreachable | integration | `pytest tests/test_admin_service_logs.py::test_partial_on_failure -x` | ❌ Wave 0 |
| ADMIN-12 | Bootstrap creates super_admin on fresh DB | integration | `pytest tests/test_admin_bootstrap.py::test_first_time_create -x` | ❌ Wave 0 |
| ADMIN-12 | Bootstrap is idempotent on subsequent starts | integration | `pytest tests/test_admin_bootstrap.py::test_idempotent -x` | ❌ Wave 0 |
| ADMIN-12 | Bootstrap respects `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=False` | integration | `pytest tests/test_admin_bootstrap.py::test_optional -x` | ❌ Wave 0 |
| (D-04) | After hoist, Phase 4 imports `from api_service.common.schemas import ApiResponse` (not `from api_service.schemas.common`) | shape test | `pytest tests/test_schemas_hoist.py::test_phase4_imports_rewritten -x` | ❌ Wave 0 |
| (D-05) | `mc:*` SCAN+DEL invocation on every model_catalog admin write | integration | `pytest tests/test_admin_model_catalog.py::test_invalidates_on_all_writes -x` | ❌ Wave 0 |
| (D-06) | `routing_config:version` INCR after every routing_settings write | integration | `pytest tests/test_admin_routing_settings.py::test_version_incremented -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q -k "admin and <module>"` — module-scoped (~2-5s)
- **Per wave merge:** `pytest tests/ -x -q -k admin` — all admin tests (~15-20s)
- **Phase gate:** `pytest tests/ --cov=api_service --cov-fail-under=80` — full suite with coverage gate before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_admin_auth.py` — covers ADMIN-01 (login/logout/refresh/me/change-password + lockout)
- [ ] `tests/test_admin_users.py` — covers ADMIN-03 (14 endpoint paths)
- [ ] `tests/test_admin_pools.py` — covers ADMIN-04 (16 endpoints; provider key encryption; upstream HTTP mock)
- [ ] `tests/test_admin_model_catalog.py` — covers ADMIN-05 + D-05 cache invalidation
- [ ] `tests/test_admin_routing_settings.py` — covers ADMIN-06 + D-06 INCR
- [ ] `tests/test_admin_dashboard.py` — covers ADMIN-07
- [ ] `tests/test_admin_audit.py` — covers ADMIN-08
- [ ] `tests/test_admin_vouchers.py` — covers ADMIN-09
- [ ] `tests/test_admin_route_monitor.py` — covers ADMIN-10
- [ ] `tests/test_admin_service_logs.py` — covers ADMIN-11 + D-03
- [ ] `tests/test_admin_bootstrap.py` — covers ADMIN-12
- [ ] `tests/test_admin_management.py` (admin-on-admin) — covers ADMIN-08-adjacent admin account CRUD
- [ ] `tests/test_pool_service.py` — unit (parameterized: 4 provider balance response shapes per Pitfall 9)
- [ ] `tests/test_audit_service.py` — unit (module cache invalidation per ADMIN-08)
- [ ] `tests/test_routing_setting_service.py` — unit (validate_tier_model_coverage logic)
- [ ] `tests/test_schemas_hoist.py` — shape test for D-04 import rewrite (Phase 4 imports must resolve from new location)
- [ ] `tests/conftest.py` (EXTEND Phase 4's) — admin-specific fixtures: `mock_admin`, `mock_super_admin`, `mock_cache_redis`, `mock_internal_client`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | bcrypt admin password hash (via Phase 1 `common/security/password.py`); login_fail_count + login_locked_until on `admin_users` |
| V3 Session Management | yes | JWT JTI blacklist (Redis db/0); rotation on `/refresh`; revocation on logout AND on change-password |
| V4 Access Control | yes | `require_active_admin` + `require_super_admin` guards; **separated from end-user auth (`require_active_user`)** to prevent cross-domain token reuse |
| V5 Input Validation | yes | Pydantic v2 schemas; slug regex `^[a-z0-9][a-z0-9._-]*$` on path params; `password_strength` check on bootstrap + change-password |
| V6 Cryptography | yes | AES-256-GCM for `pool_accounts.api_key_enc` via `common/security/crypto.py`; never log decrypted keys |
| V7 Error Handling | yes | Global handlers (Phase 1) + structured `log_event` with auto-PII masking via observability layer |
| V8 Data Protection | yes | `mask_api_key` on responses showing provider account info; password fields never returned; refresh_token_hash bcrypt'd at rest |
| V9 Communication | partial | HTTPS at reverse proxy; HMAC-signed inter-service calls (for D-03 inference HTTP, plus future Phase 8) |
| V13 API & Web Service | yes | OpenAPI generated; admin endpoints rate-limited by slowapi (Phase 4 baseline applies); login lockout per ADMIN-01 |
| V14 Configuration | yes | Bootstrap settings validated at startup (`_validate_bootstrap_settings`); `PROVIDER_SECRET_MASTER_KEY` length check |

### Known Threat Patterns for Admin Domain

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Privilege escalation via tampered cookie | Tampering | JWT signature (HS256); JTI blacklist on logout |
| Cross-domain token reuse (user token used as admin) | Spoofing | Separate cookie names (`admin_access_token` vs `user_access_token`); separate `get_current_admin` dependency; admin endpoints under `/api/v1/admin/*` |
| Audit log tampering (admin deleting own actions) | Repudiation | `admin_audit_logs` has no DELETE endpoint exposed (verify in port); `actor_admin_id` is FK with ON DELETE RESTRICT (schema concern, but DB enforces) |
| Provider API key plaintext leak via logs | Information disclosure | `mask_api_key` on outputs; never `log_event(..., key=raw_key)`; observability auto-redacts `sk-*` patterns |
| Audit row missing on successful mutation | Repudiation | Single SQLAlchemy transaction commits both audit row + business row — Pitfall 2 resolution ensures atomicity |
| Bootstrap race when scaling out workers | Tampering | MySQL `GET_LOCK("bootstrap_super_admin", 10)` exclusion; idempotent recheck after lock acquisition |
| Tier model misconfiguration → relay routes to non-existent model | Denial of service | `validate_tier_model_coverage` pre-write check in `RoutingSettingService.update_setting` |
| `mc:*` cache leak after admin update | Information disclosure (low) | D-05 SCAN+DEL; TTL safety net (max 300s stale) |
| Routing config drift between admin write and relay read | Tampering | D-06 `routing_config:version` INCR signals Phase 6 cache to reload |
| Service logs leak across services | Information disclosure | Only super_admin can fetch (`require_super_admin`); HMAC signature on inference call |
| Health check probe leaks provider key | Information disclosure | `_check_balance` sends `Authorization: Bearer {api_key}` — key never logged; only response body parsed for `total_remain` etc |

**Security review must-pass before phase ends:**
- [ ] No admin endpoint returns `password_hash`, `refresh_token_hash`, decrypted provider API key
- [ ] All admin endpoints under `/api/v1/admin/*` are protected by `require_active_admin` or `require_super_admin`
- [ ] Cookie `admin_access_token` is HttpOnly + Secure + SameSite=strict (verified via settings)
- [ ] No `safe_audit_commit` helper remains (Pitfall 2 resolution)
- [ ] No remaining import of `from gateways.*` anywhere in the merged service
- [ ] Provider key `mask_api_key` returns only first 4 + last 4 chars

## Project Constraints (from CLAUDE.md)

From `services/admin-service/CLAUDE.md` (applies to api-service admin domain):

- [ ] Controller 薄层: 只做参数提取 → service 调用 → response 构造；no ORM mutations in controllers
- [ ] Service layer: `@staticmethod` + `db: AsyncSession` first param; methods instantiate repos internally
- [ ] Repository pattern: `BaseRepository[T]` + `get_list(ListParams)`; `options=[selectinload(...)]` for eager loading
- [ ] **Gateway layer is REMOVED for Phase 5** — D-02 deletes the entire `gateways/` directory; no new gateways added
- [ ] HTTP client: ONLY `common.internal.get_internal_client(base_url, timeout=...)` (after port from admin-service per Pitfall 1)
- [ ] CPU-bound (bcrypt) wrapped in `asyncio.to_thread` via existing async helpers
- [ ] Audit record explicit per mutation (D-02b); **no `record_auto` middleware**
- [ ] Logger: `logger = logging.getLogger(__name__)`; `log_event(logger, level, "eventName", k=v)`; no string interpolation
- [ ] Sensitive info (API keys, passwords): never in logs; rely on `_redact` auto-masking + `mask_api_key`
- [ ] Settings via `from api_service.core.config import settings` singleton
- [ ] Domain exceptions from `common.core.exceptions`; do not raise plain Exception

From root `CLAUDE.md`:

- [ ] **User identity rule:** Frontend admin responses use `user_uid: str` for end-user references; **NEVER include `user_id: int`** in admin response schemas. Admin controllers internally pass `int` user_id when calling Phase 4 services (acceptable — internal boundary).
- [ ] Branch name: current `refactor/merge-api-service` covers it
- [ ] Commit messages: 中文 + conventional commits format (e.g., `feat(05): 迁移 admin 域 controllers`)
- [ ] PR target: `develop`; squash-merge

## Sources

### Primary (HIGH confidence)

**Source repository files (verified via Read):**
- `services/admin-service/src/controllers/auth.py` — 5 admin auth endpoints, cookie helpers
- `services/admin-service/src/controllers/admin_users.py` — admin-on-admin CRUD
- `services/admin-service/src/controllers/admin_audit_logs.py` — audit log endpoints + meta
- `services/admin-service/src/controllers/dashboard.py` — 5 aggregation endpoints (proxy)
- `services/admin-service/src/controllers/model_catalog_admin.py` — vendor/category/model CRUD
- `services/admin-service/src/controllers/pools.py` — Pool/PoolModel/PoolAccount CRUD
- `services/admin-service/src/controllers/route_monitor.py` — 4 endpoints (proxy)
- `services/admin-service/src/controllers/routing_settings.py` — settings CRUD
- `services/admin-service/src/controllers/service_logs.py` — 1 aggregator endpoint (proxy)
- `services/admin-service/src/controllers/user_management.py` — 14 endpoints (largest proxy)
- `services/admin-service/src/controllers/vouchers.py` — voucher CRUD (proxy)
- `services/admin-service/src/services/auth_service.py` — admin login/logout/refresh/change-password
- `services/admin-service/src/services/bootstrap_service.py` — super admin bootstrap (`GET_LOCK`)
- `services/admin-service/src/services/audit_service.py` — audit record + module cache
- `services/admin-service/src/services/management_service.py` — admin account management
- `services/admin-service/src/services/pool_service.py:1-100` — pool CRUD scaffold + balance extract
- `services/admin-service/src/services/model_catalog_service.py:1-100` — model catalog CRUD scaffold
- `services/admin-service/src/services/routing_setting_service.py` — routing settings + tier validation
- `services/admin-service/src/services/health_check_service.py` — channel probing
- `services/admin-service/src/gateways/user_management.py` — UserManagementGateway + UserStatsGateway (TO BE ELIMINATED)
- `services/admin-service/src/gateways/route_monitor.py` — RouteMonitorGateway (TO BE ELIMINATED)
- `services/admin-service/src/gateways/service_logs.py` — ServiceLogsGateway + `_REMOTE_SERVICES` (D-03 source pattern)
- `services/admin-service/src/utils/audit.py` — `safe_audit_commit` (TO BE REPLACED per Pitfall 2)
- `services/admin-service/src/utils/parsing.py` — `parse_comma_separated`
- `services/admin-service/src/schemas/common.py` — `AdminBaseResponse` + `DateTimeModel` (D-04 source)
- `services/admin-service/src/schemas/audit_log.py:1-20` — `AdminAuditCategory` Literal
- `services/admin-service/CLAUDE.md` — admin service conventions
- `services/admin-service/src/common/internal.py:1-552` (sender HMAC) — to port per Pitfall 1
- `services/api-service/api_service/main.py` — current lifespan; bootstrap to add
- `services/api-service/api_service/core/lifespan.py` — LifespanRegistry priority semantics
- `services/api-service/api_service/core/router.py` — `api_router` mount point
- `services/api-service/api_service/core/config.py` — current settings (incomplete for admin domain)
- `services/api-service/api_service/core/dependencies/admin.py` — `get_current_admin` + `get_request_meta` (Phase 3 D-06/D-07)
- `services/api-service/api_service/repositories/admin_user_repository.py` — `acquire_named_lock` verified
- `services/api-service/api_service/repositories/audit_log_repository.py` — `list_logs` signature verified
- `services/api-service/api_service/repositories/call_log_repository.py:1-80` — route monitor query methods present
- `services/api-service/api_service/repositories/pool_repository.py:1-60` — pool + pool_model + pool_account methods
- `services/api-service/api_service/common/observability.py:97-200` — `RingBufferHandler` + `get_ring_buffer`
- `services/api-service/api_service/common/http/internal_auth.py` — receiver-side HMAC (already present)
- `services/api-service/api_service/common/http/request_context.py` — IP/UA context vars
- `services/api-service/api_service/common/infra/cache.py` — Redis db/2 + `cache_get_or_fetch`
- `services/api-service/api_service/schemas/common.py` (NOT YET EXISTS — Phase 4 04-01 will create)
- `.planning/phases/05-admin-domain-controllers/05-CONTEXT.md` — D-01..D-07 locked decisions
- `.planning/phases/04-user-domain-controllers/04-CONTEXT.md` — Phase 4 D-01..D-12 (cross-reference)
- `.planning/phases/04-user-domain-controllers/04-RESEARCH.md` — Pattern donors, import translation table
- `.planning/phases/04-user-domain-controllers/04-PATTERNS.md` — Wave breakdown analog
- `.planning/REQUIREMENTS.md` — ADMIN-01..ADMIN-12 traceability
- `.planning/STATE.md` — Phase 3 decisions (D-04 repo merge, D-06/D-07 admin auth deps, D-08 user no blacklist)
- `.planning/ROADMAP.md` — phase 5 plan structure
- `CLAUDE.md` (root) — user_uid vs user_id rule, branch naming, commit conventions
- `services/admin-service/CLAUDE.md` — admin domain conventions (system reminder reinforced gateway-free + audit pattern)

### Secondary (MEDIUM confidence)

- [Phase 4 RESEARCH.md sections](file:.planning/phases/04-user-domain-controllers/04-RESEARCH.md) — Settings Gap, Translation Tables, ARQ pool wiring, security ASVS template
- [Phase 4 PATTERNS.md analog map](file:.planning/phases/04-user-domain-controllers/04-PATTERNS.md) — file-by-file port pattern (mirrored for Phase 5)
- [FastAPI cookie best practices](https://fastapi.tiangolo.com/tutorial/cookie-params/) — cookie path semantics

### Tertiary (LOW confidence)

None — research is grounded in verified source-file reads + Phase 4 cross-reference.

## Plan Difficulty Estimates

| Plan | Difficulty | Estimated Tasks | Key Files | Primary Risks |
|------|------------|-----------------|-----------|---------------|
| 05-01: Admin auth + bootstrap + D-04 hoist + Pitfall 1 prep | **MEDIUM-HIGH** | 14-18 | Wave 0: `common/schemas.py` hoist + Phase 4 import rewrites + `common/internal.py` port (Pitfall 1) + Settings keys (9 new) + `core/policies.py` extend; Wave 1: `controllers/admin/auth.py` + `controllers/admin/admin_users.py` + `controllers/admin/audit_logs.py` + `services/admin/{auth,management,audit,bootstrap}_service.py` + `schemas/admin/{auth,admin_user,audit_log}.py` + `main.py` lifespan registration | (1) D-04 schema hoist requires Phase 4 already landed; (2) `common/internal.py` port + dedup with receiver-side signing primitives; (3) Bootstrap priority placement; (4) Pitfall 8 BaseResponse rename touches all Phase 4 + Phase 5 files |
| 05-02: Pool/Model/Routing CRUD + D-05 + D-06 + HealthCheck | **HIGH** | 16-22 | controllers/admin/{pools,model_catalog,routing_settings}.py + services/admin/{pool,model_catalog,routing_setting,health_check}_service.py + schemas/admin/{pool,model_catalog,routing_setting}.py + ARQ cron registration for health checks | (1) `pool_service.py` 599 lines — largest single file with encrypt/decrypt + upstream HTTP; (2) D-05 SCAN/DEL invocation must wire to every write method (10+ sites); (3) D-06 INCR on 2 methods; (4) `validate_tier_model_coverage` cross-table validation; (5) Pitfall 4 — drop `resolve_for_internal`; (6) Pitfall 9 — 4 provider balance shapes need test coverage; (7) HealthCheck cron registration (O-2 + O-5) |
| 05-03: Proxy elimination (5 services replacing 5 gateways) + delete gateway dir | **MEDIUM** | 12-16 | controllers/admin/{users,dashboard,vouchers,route_monitor,service_logs}.py + services/admin/{admin_user,dashboard,voucher,route_monitor,service_logs}_service.py + schemas/admin/{user_management,route_monitor,service_logs,voucher}.py + DELETE admin-service/gateways/ | (1) `admin_user_service.py` is largest new file (~400 lines); (2) `dashboard_service.py` requires NEW aggregate methods on `BillingRepository` / `CallLogRepository` that don't exist today (must be checked + added); (3) Pitfall 2 — replace all `safe_audit_commit` call sites; (4) Pitfall 3 — naming collision rename; (5) Service logs D-03 — verify inference path (O-3) |

**Recommended task ordering (cross-plan):**
1. Wave 0 (foundational, MUST land first in 05-01):
   - D-04 hoist: create `api_service/common/schemas.py` with `BaseResponse`, `ErrorResponse`, `ApiResponse[T]`, `DateTimeModel`
   - Rewrite Phase 4 imports (`grep -rln "api_service.schemas.common"` audit)
   - Add 9 new Settings keys (Settings Gap table)
   - Port `admin-service/common/internal.py` → `api_service/common/internal.py` with dedup
   - Add `require_active_admin` + `require_super_admin` to `core/policies.py`
   - Add `AdminConflictException` + `AdminPermissionDeniedException` to `common/core/exceptions.py`
2. Wave 1 (plan 05-01): admin auth + admin-on-admin + audit + bootstrap → 11 admin-domain endpoints + lifespan hook
3. Wave 2 (plan 05-02): Pool + Model Catalog + Routing Settings → 28+ endpoints + D-05 + D-06 + health check cron
4. Wave 3 (plan 05-03): 5 proxy-elimination services → 28 endpoints + delete `gateways/` + drop `safe_audit_commit`
5. Wave 4 (plan 05-03 close-out): `api_router.include_router(admin_router, prefix="/admin")` + integration tests for end-to-end admin flows

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies verified in Phase 4 research; no new packages
- Architecture / patterns: HIGH — sourced from verified file reads (controllers + services)
- Pitfalls: HIGH — translation tables built from side-by-side Read of admin-service + api-service + Phase 4 RESEARCH cross-reference
- D-05/D-06 hook design: HIGH — pattern is simple SCAN/DEL + INCR, mirrors Phase 4 cache.py fail-open style
- `common/internal.py` port (Pitfall 1): MEDIUM — 552-line port + receiver-side dedup is mechanical but non-trivial; allow 1-2 days for plan
- Cookie path (Pattern 1 / O-1): MEDIUM-HIGH — source code has explicit operational comment, but CONTEXT `<specifics>` suggests otherwise; user confirmation needed
- `safe_audit_commit` removal (Pitfall 2): MEDIUM — architectural argument is sound but is a behavior change; user confirmation recommended

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (30 days for migration phases — source code is frozen, but Phase 4 progress will affect dependency graph)
