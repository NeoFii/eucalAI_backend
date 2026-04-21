# Refactor Overview Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps between `refactor/overview.md` and the current backend implementation.

**Architecture:** Preserve the existing service boundaries and move the remaining direct data-access calls behind service-local repositories. Keep cross-service calls in Gateway modules, add tests for these boundaries, and update migration/docs drift without changing API contracts.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async sessions, Alembic, pytest.

---

### Priority 1: Add Guardrail Tests

**Files:**
- Modify: `tests/architecture/test_no_cross_service_import.py`
- Modify: `tests/test_migration_structure.py`
- Modify: `tests/test_refactor_cleanup.py`

- [x] Add a test that selected endpoint/service files no longer call `db.execute()` or build `select()` statements directly.
- [x] Add a test that Gateway modules use `BaseGateway` consistently.
- [x] Add a test that the API key soft-delete migration creates and drops a `deleted_at` index.
- [x] Add a test that `docs/PROJECT_STRUCTURE.md` no longer documents deleted legacy files.
- [x] Run the new tests and verify they fail before implementation.

### Priority 2: Move Remaining Direct SQL Behind Repositories

**Files:**
- Modify: `src/admin_service/api/v1/endpoints/internal.py`
- Modify: `src/admin_service/repositories/admin_user_repository.py`
- Modify: `src/admin_service/services/bootstrap_service.py`
- Modify: `src/user_service/api/v1/endpoints/internal.py`
- Modify: `src/user_service/repositories/user_repository.py`
- Modify: `src/testing_service/repositories/model_repository.py`
- Modify: `src/testing_service/services/model_service.py`

- [x] Move internal admin/user lookup and user count queries into repositories.
- [x] Move bootstrap super-admin lookup/count and named-lock SQL into `AdminUserRepository`.
- [x] Move testing-service vendor/model/provider/offering lookup, count, and category-map deletion queries into repositories.
- [x] Keep business mutation and transaction boundaries in services.

### Priority 3: Align Gateway and Migration Details

**Files:**
- Modify: `src/user_service/gateway.py`
- Modify: `src/testing_service/gateway.py`
- Modify: `src/router_service/gateway.py`
- Modify: `migrations/user_service/versions/20260420_11_add_deleted_at_to_user_api_keys.py`

- [x] Add a user invitation gateway interface.
- [x] Make testing and router gateway classes inherit `BaseGateway`.
- [x] Add `ix_user_api_keys_deleted_at` creation and removal to the migration.

### Priority 4: Update Documentation and Verify

**Files:**
- Modify: `docs/PROJECT_STRUCTURE.md`

- [x] Replace stale `schemas.py`, legacy client, and `benchmarking/` entries with the current package layout.
- [x] Run targeted architecture/service tests.
- [ ] Run full test suite.
- [ ] Merge the branch into `main`.
- [ ] Push `origin main`.
