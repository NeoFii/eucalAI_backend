# User Service Refactor Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining `user_service` overview refactor work so the service matches the approved repository/query/schema boundaries instead of only passing compatibility tests.

**Architecture:** First tighten the shared `common.db` primitives so repositories can own pagination and time-range validation. Then migrate `user_service` schemas away from `schemas_legacy.py`, move remaining SQL/data-access work out of services into repositories, and rerun the targeted plus boundary suites before integration.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, Alembic, pytest, uv

---

### Task 1: Strengthen Common Query and Repository Primitives

**Files:**
- Modify: `src/common/db/query.py`
- Modify: `src/common/db/repository.py`
- Modify: `tests/test_common.py`

- [ ] **Step 1: Write failing tests for `ListParams` time-window defaults and `BaseRepository.get_list()`**
- [ ] **Step 2: Run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_common.py` and verify the new assertions fail**
- [ ] **Step 3: Implement `ListParams.start/end/time_field/max_span_days`, `validate_time_range()`, and repository list helpers**
- [ ] **Step 4: Re-run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_common.py` and verify it passes**

### Task 2: Replace Legacy Schema Re-exports With Real Split Modules

**Files:**
- Modify: `src/user_service/schemas/auth.py`
- Modify: `src/user_service/schemas/billing.py`
- Modify: `src/user_service/schemas/billing_admin.py`
- Modify: `src/user_service/schemas/__init__.py`
- Modify: `tests/test_user_rebuild.py`
- Modify: `tests/test_user_auth_billing_refactor.py`

- [ ] **Step 1: Write failing tests that assert split schema modules define the real models instead of importing `schemas_legacy`**
- [ ] **Step 2: Run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user_rebuild.py tests/test_user_auth_billing_refactor.py` and verify failure**
- [ ] **Step 3: Move auth and billing schema definitions into the split modules, keeping current contracts stable**
- [ ] **Step 4: Re-run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user_rebuild.py tests/test_user_auth_billing_refactor.py` and verify pass**

### Task 3: Finish Repository Boundary Migration for Email and Usage Stats

**Files:**
- Modify: `src/user_service/repositories/email_code_repository.py`
- Modify: `src/user_service/repositories/usage_stat_repository.py`
- Modify: `src/user_service/services/email_service.py`
- Modify: `src/user_service/services/usage_stat_service.py`
- Modify: `tests/test_user.py`
- Modify: `tests/test_user_rebuild.py`

- [ ] **Step 1: Write failing tests for email-code and usage-stat repository ownership of the remaining DB work**
- [ ] **Step 2: Run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user.py tests/test_user_rebuild.py` and verify failure**
- [ ] **Step 3: Add repository methods for email-code queries/mutations and usage-stat aggregation lookups, then update services to use them**
- [ ] **Step 4: Re-run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user.py tests/test_user_rebuild.py` and verify pass**

### Task 4: Adopt Shared ListParams/PaginatedResult in User-Service Billing Queries

**Files:**
- Modify: `src/user_service/repositories/balance_tx_repository.py`
- Modify: `src/user_service/repositories/topup_order_repository.py`
- Modify: `src/user_service/repositories/usage_stat_repository.py`
- Modify: `src/user_service/services/balance_service.py`
- Modify: `src/user_service/services/topup_order_service.py`
- Modify: `src/user_service/services/usage_stat_service.py`
- Modify: `src/user_service/api/v1/endpoints/billing.py`
- Modify: `src/user_service/api/v1/endpoints/admin_billing.py`
- Modify: `tests/test_user_rebuild.py`

- [ ] **Step 1: Write failing tests that exercise `ListParams`-based time validation and paginated repository results through billing endpoints/services**
- [ ] **Step 2: Run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user_rebuild.py` and verify failure**
- [ ] **Step 3: Refactor billing endpoints/services/repositories to use `ListParams` and `PaginatedResult` as the shared query path**
- [ ] **Step 4: Re-run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user_rebuild.py` and verify pass**

### Task 5: Final Verification and Integration

**Files:**
- Verify only

- [ ] **Step 1: Run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_common.py tests/test_user_rebuild.py tests/test_user_auth_billing_refactor.py tests/test_user_api_key_repository.py`**
- [ ] **Step 2: Run `uv --cache-dir /tmp/uv-cache run pytest -q tests/test_user.py tests/test_architecture_boundaries.py tests/test_service_environment.py tests/test_schema_drift.py tests/test_schema_ownership.py`**
- [ ] **Step 3: Review `git diff --stat` and `git status --short` for the worktree**
- [ ] **Step 4: Merge `user-service-refactor` back to `main` and push `origin/main` only after both suites pass**
