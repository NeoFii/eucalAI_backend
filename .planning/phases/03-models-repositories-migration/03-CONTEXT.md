# Phase 3: Models & Repositories Migration - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

将 user-service（9 个 ORM models）和 admin-service（7 个 ORM models）迁移到 api-service/models/，合并 14 个 repository 为 10 个按域分组的 repository，迁移 auth 依赖函数（get_current_user, get_current_admin）。

完成后所有 ORM models 可从 `api_service.models` 导入，repository 层可执行基本 CRUD，auth 依赖可正确解析当前用户/管理员。

不包含：controller 端点（Phase 4/5）、业务逻辑 service 层（Phase 4/5）、relay 相关逻辑（Phase 6）。

</domain>

<decisions>
## Implementation Decisions

### ORM Model 类名映射
- **D-01:** ORM 类名与表名对齐重命名：
  - `SupportedModel` → `ModelCatalog`（表 `model_catalog`）
  - `PoolModel` → `PoolModelConfig`（表 `pool_model_configs`）
  - `SupportedModelCategoryMap` → `ModelCatalogCategoryMap`（表 `model_catalog_category_map`）
- **D-02:** 其他 model 类名保持不变（User, AdminUser, Pool, PoolAccount 等已与表名一致）
- **D-03:** 所有 models 继承 `api_service.common.infra.db.base.Base`（Phase 2 D-15 延续）

### Repository 合并策略
- **D-04:** 按域合并为 10 个 repository：
  1. `UserRepository` — user + session + email_code
  2. `ApiKeyRepository` — 保持独立
  3. `BillingRepository` — balance_tx + topup_order + usage_stat
  4. `CallLogRepository` — 保持独立，包含 route_monitor 查询
  5. `VoucherRepository` — 保持独立
  6. `AdminUserRepository` — 保持独立
  7. `AuditLogRepository` — 保持独立
  8. `ModelCatalogRepository` — 保持独立，含 vendor/category 操作
  9. `PoolRepository` — pool + pool_model_config + pool_account
  10. `RoutingSettingRepository` — 保持独立
- **D-05:** Repository 方法签名保持与原服务一致，仅调整 import 路径和 model 类名

### Auth 依赖架构
- **D-06:** Auth 依赖按域拆分文件：
  - `api_service/core/dependencies/user.py` — `get_current_user`
  - `api_service/core/dependencies/admin.py` — `get_current_admin`, `get_optional_current_admin`, `get_request_meta`
  - `api_service/core/dependencies/__init__.py` — 统一导出
- **D-07:** Admin auth 保留 token blacklist 检查（`is_token_blacklisted`）
- **D-08:** User auth 不做 blacklist 检查（保持现有行为）
- **D-09:** 两者共用 `get_db` 从 `api_service.core.db` 导入

### 文件组织
- **D-10:** Models 放在 `api_service/models/` 包下，按表/实体拆分文件
- **D-11:** Repositories 放在 `api_service/repositories/` 包下，按域分文件
- **D-12:** `api_service/models/__init__.py` 导出所有 model 类（供 Alembic metadata 和 downstream 使用）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source Models (migration source — read for column definitions and relationships)
- `services/user-service/src/models/` — 9 个 user-domain ORM models
- `services/admin-service/src/models/` — 7 个 admin-domain ORM models（注意类名需重命名）

### Source Repositories (migration source — read for method signatures)
- `services/user-service/src/repositories/` — 9 个 user-domain repositories
- `services/admin-service/src/repositories/` — 5 个 admin-domain repositories

### Source Auth Dependencies
- `services/user-service/src/core/dependencies.py` — get_current_user 实现
- `services/admin-service/src/core/dependencies.py` — get_current_admin + get_optional_current_admin + get_request_meta

### Phase 2 产出（已就绪）
- `services/api-service/api_service/core/db.py` — get_db, Base 导出
- `services/api-service/api_service/common/infra/db/base.py` — Base(DeclarativeBase) + Mixins
- `services/api-service/api_service/models/__init__.py` — 当前为空占位，Phase 3 填充

### Architecture Reference
- `docs/architecture-refactoring.md` — 合并架构方案
- `services/api-service/migrations/versions/20260519_baseline.py` — 22 张表最终 DDL（列名/类型权威参考）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Base` + Mixins（TimestampMixin, SoftDeleteMixin）已在 `common/infra/db/base.py`
- `get_db` 异步生成器已在 `core/db.py`
- `decode_token` / `get_token_jti` 已在 `common/utils/jwt.py`
- `is_token_blacklisted` 已在 `common/token_blacklist.py`
- `set_uid` observability helper 已在 `common/observability.py`
- 异常类（AuthenticationException, InvalidTokenException 等）已在 `common/core/exceptions.py`

### Established Patterns
- ORM model 定义：`class Xxx(Base)` + `__tablename__` + Column 定义
- Repository 模式：纯静态方法类，接收 `db: AsyncSession` 参数
- Auth 依赖：FastAPI `Depends()` 链式注入，Cookie + Bearer 双通道

### Integration Points
- `api_service/models/__init__.py` — Alembic `_env_shared.py` 通过此文件加载 metadata
- `api_service/core/dependencies/` — Phase 4/5 controller 通过 Depends 使用
- `api_service/repositories/` — Phase 4/5 service 层调用

</code_context>

<specifics>
## Specific Ideas

- admin-service 的 `model_catalog.py` 包含 4 个类（ModelVendor, ModelCategory, SupportedModel, SupportedModelCategoryMap），迁移时拆为独立文件或保持合并均可，建议按表拆分
- PoolRepository 合并后方法较多（pool CRUD + model_config CRUD + account CRUD），可考虑内部按 section 组织

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 3-Models & Repositories Migration*
*Context gathered: 2026-05-19*
