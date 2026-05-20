---
phase: 03-models-repositories-migration
plan: "01"
subsystem: database
tags: [sqlalchemy, orm, models, migration]

requires:
  - phase: 02-database-redis-infrastructure
    provides: Base(DeclarativeBase) + Mixins in common/infra/db/base.py

provides:
  - 20 ORM model classes importable from api_service.models
  - 3 IntEnum classes (AdminRole, AdminStatus, PoolAccountStatus)
  - Unified models/__init__.py with __all__ export
  - D-01 class renames applied (ModelCatalog, ModelCatalogCategoryMap, PoolModelConfig)

affects: [03-02-repositories, 03-03-auth-dependencies, phase-4, phase-5, phase-6]

tech-stack:
  added: []
  patterns:
    - "ORM models inherit api_service.common.infra.db.base.Base"
    - "Relationship references use string class names for lazy resolution"
    - "Models organized one-file-per-entity under api_service/models/"

key-files:
  created:
    - services/api-service/api_service/models/enums.py
    - services/api-service/api_service/models/user.py
    - services/api-service/api_service/models/user_session.py
    - services/api-service/api_service/models/email_verification_code.py
    - services/api-service/api_service/models/user_api_key.py
    - services/api-service/api_service/models/balance_transaction.py
    - services/api-service/api_service/models/topup_order.py
    - services/api-service/api_service/models/api_call_log.py
    - services/api-service/api_service/models/usage_stat.py
    - services/api-service/api_service/models/voucher_redemption_code.py
    - services/api-service/api_service/models/admin_user.py
    - services/api-service/api_service/models/admin_audit_log.py
    - services/api-service/api_service/models/audit_action_definition.py
    - services/api-service/api_service/models/model_catalog.py
    - services/api-service/api_service/models/pool.py
    - services/api-service/api_service/models/routing_setting.py
    - services/api-service/tests/test_models_import.py
  modified:
    - services/api-service/api_service/models/__init__.py

key-decisions:
  - "Plan count correction: 20 model classes (not 19) — RoutingSetting was undercounted in plan"
  - "schema_version and alembic_version tables excluded from metadata test (Alembic-managed, not ORM models)"

patterns-established:
  - "One model per file, named after the entity (snake_case)"
  - "All models inherit Base from api_service.common.infra.db.base"
  - "Enums in separate enums.py module, imported by models that need them"
  - "Relationship strings use new class names post-D-01 rename"

requirements-completed: [USER-02, USER-03, ADMIN-02]

duration: 11min
completed: 2026-05-18
---

# Phase 3 Plan 01: ORM Models Consolidation Summary

**Migrated 20 ORM models (9 user-domain + 11 admin-domain) into api_service/models/ with 3 D-01 class renames and zero circular dependencies**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-18T17:06:42Z
- **Completed:** 2026-05-18T17:17:26Z
- **Tasks:** 17
- **Files created:** 17

## Accomplishments
- All 20 ORM model classes importable from `api_service.models` without circular dependencies
- 3 classes renamed per D-01 decision: SupportedModel→ModelCatalog, SupportedModelCategoryMap→ModelCatalogCategoryMap, PoolModel→PoolModelConfig
- 28 parametrized tests verify tablenames, metadata registration, and absence of old class names
- All relationship strings updated to reference new class names

## Task Commits

1. **Task 01: 创建 enums 模块** - `988ba15`
2. **Task 02: 迁移 User model** - `9b6f103`
3. **Task 03: 迁移 UserSession model** - `b8ff6c6`
4. **Task 04: 迁移 EmailVerificationCode model** - `002035c`
5. **Task 05: 迁移 UserApiKey model** - `410c049`
6. **Task 06: 迁移 BalanceTransaction model** - `58857c3`
7. **Task 07: 迁移 TopupOrder model** - `0341ce3`
8. **Task 08: 迁移 ApiCallLog model** - `ff1e988`
9. **Task 09: 迁移 UsageStat model** - `f33480a`
10. **Task 10: 迁移 VoucherRedemptionCode model** - `653e935`
11. **Task 11: 迁移 AdminUser model** - `6063175`
12. **Task 12: 迁移 AdminAuditLog + AuditActionDefinition** - `66b007b`
13. **Task 13: 迁移 ModelCatalog 相关 models** - `439ce14`
14. **Task 14: 迁移 Pool 相关 models** - `8820dff`
15. **Task 15: 迁移 RoutingSetting model** - `82e6e01`
16. **Task 16: 创建 models/__init__.py 统一导出** - `93d75d6`
17. **Task 17: 编写 model 导入测试** - `c0c33ec`

## Decisions Made
- Plan stated 19 model classes but actual count is 20 (RoutingSetting was undercounted). Exported all 20 correctly.
- `schema_version` and `alembic_version` tables are Alembic-managed (not ORM models), excluded from metadata assertion in tests.

## Deviations from Plan

None - plan executed exactly as written (minor count correction documented above).

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Self-Check: PASSED

All verification commands pass:
- `from api_service.models import ...` — all 20 models + 3 enums importable
- `import api_service.models` — no circular dependency
- `Base.metadata.tables` — contains all 20 ORM tables
- `pytest tests/test_models_import.py` — 28/28 passed

## Next Phase Readiness
Ready for 03-02 (Repository layer migration). All model classes are available for repository imports.

---
*Phase: 03-models-repositories-migration*
*Completed: 2026-05-18*
