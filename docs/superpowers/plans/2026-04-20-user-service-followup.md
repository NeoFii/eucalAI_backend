# User Service Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the highest-confidence user-service behavior gaps, then leave a clean baseline for the remaining billing/key work.

**Architecture:** Keep the current merged `backend_app + user_service` structure intact. Only touch user-service auth behavior, registration compensation, and stale documentation/tests that no longer match the current architecture.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, Pydantic, Alembic

---

### Task 1: Fix Verify Email Behavior

**Files:**
- Modify: `src/user_service/api/v1/endpoints/auth.py`
- Test: `tests/test_review_fixes.py`

- [ ] **Step 1: Write the failing test**
Add an endpoint-level test proving `/auth/verify-email` calls `AuthService.verify_email()` rather than only validating the code.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_review_fixes.py -k verify_email -v`
Expected: FAIL because the endpoint does not update user state through the service.

- [ ] **Step 3: Write minimal implementation**
Change the endpoint to delegate to `AuthService.verify_email()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_review_fixes.py -k verify_email -v`
Expected: PASS

### Task 2: Persist Invitation Release Compensation Work

**Files:**
- Modify: `src/user_service/services/auth_service.py`
- Test: `tests/test_review_fixes.py`

- [ ] **Step 1: Write the failing test**
Add a test proving registration commit failure writes an `InvitationReleaseOutbox` record when release back to admin-service fails.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_review_fixes.py -k invitation -v`
Expected: FAIL because the code only tries direct release and drops compensation state.

- [ ] **Step 3: Write minimal implementation**
On local registration commit failure, keep the direct release attempt, but persist an outbox row if that release fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_review_fixes.py -k invitation -v`
Expected: PASS

### Task 3: Clean Stale User-Service Documentation/Test Baseline

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `TODO.md`
- Modify: `tests/test_architecture_boundaries.py`
- Modify: `tests/test_schema_ownership.py`

- [ ] **Step 1: Write or update the failing assertions only where needed**
Adjust stale references that still describe removed user-service files or outdated ownership assumptions.

- [ ] **Step 2: Run targeted verification**

Run: `pytest tests/test_architecture_boundaries.py tests/test_schema_ownership.py -v`
Expected: FAIL on stale assumptions before updates, PASS after updates.

- [ ] **Step 3: Write minimal implementation**
Update docs/tests to match the current user-service state.

- [ ] **Step 4: Re-run verification**

Run: `pytest tests/test_architecture_boundaries.py tests/test_schema_ownership.py -v`
Expected: PASS

### Task 4: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run focused user-service verification**

Run: `pytest tests/test_user.py tests/test_review_fixes.py tests/test_architecture_boundaries.py tests/test_schema_ownership.py -v`
Expected: PASS, or explicit report of remaining failures outside this change set.
