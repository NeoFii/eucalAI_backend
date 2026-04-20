# User Service Overview Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `user_service` to the approved repository/policy/gateway/schema structure while preserving the existing HTTP API except for the explicitly approved fixes.

**Architecture:** First add the minimal `common` primitives that the refactor depends on. Then migrate API key flow to validate the new structure, and finally migrate auth and billing onto the same boundaries while keeping endpoint paths and request contracts stable.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, Alembic, pytest

---

### Task 1: Add Common Refactor Primitives

**Files:**
- Modify: `src/common/db/base.py`
- Create: `src/common/db/repository.py`
- Create: `src/common/db/query.py`
- Create: `src/common/gateway/base.py`
- Modify: `src/common/db/__init__.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: Write failing tests for SoftDeleteMixin, BaseRepository, ListParams, and BaseGateway**
- [ ] **Step 2: Run the targeted common tests and verify they fail for the missing primitives**
- [ ] **Step 3: Implement the minimal common primitives**
- [ ] **Step 4: Re-run the targeted common tests and verify they pass**

### Task 2: Migrate API Key Flow

**Files:**
- Modify: `src/user_service/models/user_api_key.py`
- Create: `src/user_service/repositories/__init__.py`
- Create: `src/user_service/repositories/api_key_repository.py`
- Create: `src/user_service/policies.py`
- Create: `src/user_service/schemas/__init__.py`
- Create: `src/user_service/schemas/common.py`
- Create: `src/user_service/schemas/keys.py`
- Modify: `src/user_service/services/api_key_service.py`
- Modify: `src/user_service/api/v1/endpoints/keys.py`
- Modify: `src/user_service/models/__init__.py`
- Create: `migrations/user_service/versions/20260420_12_user_api_keys_soft_delete_refactor.py`
- Test: `tests/test_user_rebuild.py`
- Test: `tests/test_user.py`

- [ ] **Step 1: Write failing tests for soft-delete API key behavior and key schema import compatibility**
- [ ] **Step 2: Run the targeted user tests and verify the new expectations fail**
- [ ] **Step 3: Implement SoftDeleteMixin on `UserApiKey`, repository, policy, and key schema split**
- [ ] **Step 4: Refactor API key service and endpoint imports to use the new repository and schemas**
- [ ] **Step 5: Re-run the targeted API key tests and verify they pass**

### Task 3: Migrate Auth Dependencies, Policies, and Gateway

**Files:**
- Create: `src/user_service/gateway.py`
- Create: `src/user_service/repositories/user_repository.py`
- Create: `src/user_service/repositories/session_repository.py`
- Create: `src/user_service/repositories/email_code_repository.py`
- Create: `src/user_service/schemas/auth.py`
- Modify: `src/user_service/dependencies.py`
- Modify: `src/user_service/services/auth_service.py`
- Modify: `src/user_service/services/email_service.py`
- Modify: `src/user_service/api/v1/endpoints/auth.py`
- Modify: `src/user_service/services/__init__.py`
- Delete: `src/user_service/services/admin_client.py`
- Test: `tests/test_user.py`

- [ ] **Step 1: Write failing tests for dependency/policy split and disabled reset-password restriction**
- [ ] **Step 2: Run the targeted auth tests and verify they fail for the expected reasons**
- [ ] **Step 3: Implement auth repositories, gateway migration, auth schema split, and policy wiring**
- [ ] **Step 4: Delete the old admin client and update imports**
- [ ] **Step 5: Re-run the targeted auth tests and verify they pass**

### Task 4: Migrate Billing Repositories and Safe Response Schemas

**Files:**
- Create: `src/user_service/repositories/balance_tx_repository.py`
- Create: `src/user_service/repositories/topup_order_repository.py`
- Create: `src/user_service/repositories/usage_stat_repository.py`
- Create: `src/user_service/schemas/billing.py`
- Create: `src/user_service/schemas/billing_admin.py`
- Modify: `src/user_service/services/balance_service.py`
- Modify: `src/user_service/services/topup_order_service.py`
- Modify: `src/user_service/services/usage_stat_service.py`
- Modify: `src/user_service/api/v1/endpoints/billing.py`
- Modify: `src/user_service/api/v1/endpoints/admin_billing.py`
- Test: `tests/test_user_rebuild.py`
- Test: `tests/test_user.py`

- [ ] **Step 1: Write failing tests for safe user billing responses and `/billing/balance` fields**
- [ ] **Step 2: Run the targeted billing tests and verify they fail correctly**
- [ ] **Step 3: Implement billing repositories and safe schema split**
- [ ] **Step 4: Refactor billing services and endpoints to use the new structures**
- [ ] **Step 5: Re-run the targeted billing tests and verify they pass**

### Task 5: Remove Old Schema Entrypoint and Verify

**Files:**
- Delete: `src/user_service/schemas.py`
- Modify: `src/user_service/__init__.py`
- Modify: `src/user_service/api/v1/endpoints/*.py`
- Modify: `src/user_service/services/*.py`
- Test: `tests/test_user.py`
- Test: `tests/test_user_rebuild.py`
- Test: `tests/test_architecture_boundaries.py`
- Test: `tests/test_service_environment.py`
- Test: `tests/test_schema_drift.py`
- Test: `tests/test_schema_ownership.py`

- [ ] **Step 1: Write any final failing compatibility tests for old import paths or exposure rules**
- [ ] **Step 2: Run the final targeted suite and confirm failures are due to remaining old imports**
- [ ] **Step 3: Delete `schemas.py` and finish import migration**
- [ ] **Step 4: Run the full verification suite for this refactor**
