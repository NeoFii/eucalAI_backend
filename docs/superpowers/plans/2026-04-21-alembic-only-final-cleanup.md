# Alembic-Only Final Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove runtime schema creation entirely, enforce Alembic-head fail-fast at service startup, and finish the last repository cleanup around tests/docs/runtime entrypoints.

**Architecture:** Introduce one shared schema-version check path for runtime startup, delete `init_db()` / `create_all` execution from service entrypoints, and make `bootstrap-databases` plus `uv run migrate ...` the only schema advancement flow. Keep the implementation single-path: no compatibility flags, no bypass envs, no fallback auto-init.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, existing service-local migration CLI in `scripts/migrate.py`

---

## File Structure

**Create**
- `src/common/db/schema_version.py`
  Purpose: shared Alembic revision inspection/check helpers for runtime startup.
- `tests/test_alembic_runtime.py`
  Purpose: focused fail-fast tests for runtime schema version checks and “no runtime init_db” enforcement.

**Modify**
- `src/common/db/runtime.py`
  Purpose: remove runtime schema-creation entrypoint if unused after cutover.
- `src/common/db/__init__.py`
  Purpose: export the new schema-version helper if it becomes part of the shared runtime surface.
- `src/backend_app/lifecycle.py`
  Purpose: replace `AUTO_INIT_DB`/`init_db()` behavior with Alembic head checks.
- `src/backend_app/main.py`
  Purpose: keep entrypoint wiring aligned with the new lifecycle-only startup path.
- `src/admin_service/main.py`
  Purpose: standalone admin startup must fail fast on Alembic mismatch and must not auto-create schema.
- `src/testing_service/main.py`
  Purpose: standalone testing startup must fail fast on Alembic mismatch and must not auto-create schema.
- `src/admin_service/bootstrap_superadmin.py`
  Purpose: remove schema-init responsibilities from the bootstrap CLI.
- `src/common/config.py`
  Purpose: remove `AUTO_INIT_DB` from shared runtime config.
- `src/testing_service/config.py`
  Purpose: remove `auto_init_db` property / dead config path if it only wraps removed behavior.
- `scripts/migrate.py`
  Purpose: reuse or expose the minimum migration metadata needed by runtime head checks without pulling runtime into script-only patterns.
- `scripts/bootstrap_service_databases.py`
  Purpose: keep this as the canonical “upgrade databases” operational entrypoint and align help text/messages.
- `migrations/README.md`
  Purpose: document Alembic-only schema ownership and fail-fast startup behavior.
- `docs/ARCHITECTURE.md`
  Purpose: remove any implication of runtime schema creation.
- `docs/DATABASE.md`
  Purpose: document required migrate-before-start workflow.
- `docs/schema-ownership.md`
  Purpose: align ownership docs with Alembic-only startup rules.
- `tests/test_phase4_runtime.py`
  Purpose: align runtime assertions with Alembic-only startup.
- `tests/test_internal_contracts.py`
  Purpose: remove any assumptions about `AUTO_INIT_DB`-driven startup.
- `tests/test_migration_structure.py`
  Purpose: assert Alembic is the only schema-management path.
- `tests/test_refactor_cleanup.py`
  Purpose: lock removal of runtime schema-creation paths.
- `tests/test_review_fixes.py`
  Purpose: remove stale assumptions about runtime `init_db()` calls.

**Do Not Modify Unless Blocked**
- `migrations/*/versions/*`
  Purpose: existing Alembic history remains source of truth; do not rewrite revision history.

### Task 1: Lock Alembic-Only Runtime Behavior With Failing Tests

**Files:**
- Create: `tests/test_alembic_runtime.py`
- Modify: `tests/test_phase4_runtime.py`
- Modify: `tests/test_migration_structure.py`
- Modify: `tests/test_refactor_cleanup.py`

- [ ] **Step 1: Write the failing runtime guard tests**

```python
def test_backend_app_runtime_does_not_call_init_db():
    source = (ROOT / "src" / "backend_app" / "lifecycle.py").read_text(encoding="utf-8")
    assert "init_db(" not in source


def test_standalone_services_do_not_call_init_db():
    admin_main = (ROOT / "src" / "admin_service" / "main.py").read_text(encoding="utf-8")
    testing_main = (ROOT / "src" / "testing_service" / "main.py").read_text(encoding="utf-8")
    assert "init_db(" not in admin_main
    assert "init_db(" not in testing_main


def test_runtime_schema_version_check_fails_when_current_revision_is_not_head(monkeypatch):
    from common.db.schema_version import ensure_database_at_head

    monkeypatch.setattr("common.db.schema_version.get_current_revision", lambda *_: "rev_old")
    monkeypatch.setattr("common.db.schema_version.get_head_revision", lambda *_: "rev_head")

    with pytest.raises(RuntimeError):
        ensure_database_at_head(...)
```

- [ ] **Step 2: Run the focused tests to verify they fail on current code**

Run:
```bash
uv --cache-dir /tmp/uv-cache run pytest tests/test_alembic_runtime.py tests/test_phase4_runtime.py tests/test_migration_structure.py tests/test_refactor_cleanup.py -q
```

Expected:
- FAIL because `schema_version.py` does not exist yet
- FAIL because runtime files still contain `init_db(` / `AUTO_INIT_DB` references

- [ ] **Step 3: Add a cleanup assertion for docs/tooling**

```python
def test_docs_and_scripts_describe_alembic_as_only_schema_path():
    readme = (ROOT / "migrations" / "README.md").read_text(encoding="utf-8")
    assert "唯一 schema 真理" in readme
    assert "create_all" not in readme
```

- [ ] **Step 4: Re-run the focused tests and capture the failing list**

Run:
```bash
uv --cache-dir /tmp/uv-cache run pytest tests/test_alembic_runtime.py tests/test_phase4_runtime.py tests/test_migration_structure.py tests/test_refactor_cleanup.py -q
```

Expected:
- FAIL with a stable set of missing helper / stale runtime-path failures

- [ ] **Step 5: Commit the red test baseline**

```bash
git add tests/test_alembic_runtime.py tests/test_phase4_runtime.py tests/test_migration_structure.py tests/test_refactor_cleanup.py
git commit -m "test: lock alembic-only runtime behavior"
```

### Task 2: Add Shared Alembic Head Check And Remove Runtime Schema Creation

**Files:**
- Create: `src/common/db/schema_version.py`
- Modify: `src/common/db/runtime.py`
- Modify: `src/common/db/__init__.py`
- Modify: `src/backend_app/lifecycle.py`
- Modify: `src/admin_service/main.py`
- Modify: `src/testing_service/main.py`
- Modify: `src/admin_service/bootstrap_superadmin.py`
- Test: `tests/test_alembic_runtime.py`
- Test: `tests/test_phase4_runtime.py`

- [ ] **Step 1: Implement the shared Alembic head-check helper**

```python
def build_service_alembic_config(service_name: str, url: str) -> Config:
    ...


def get_head_revision(service_name: str) -> str:
    ...


def get_current_revision(service_name: str, url: str) -> str | None:
    ...


def ensure_database_at_head(*, service_name: str, url: str) -> None:
    current = get_current_revision(service_name, url)
    head = get_head_revision(service_name)
    if current != head:
        raise RuntimeError(
            f"{service_name} database is at {current!r}, expected {head!r}; "
            f"run: uv run migrate --service {service_name} upgrade head"
        )
```

- [ ] **Step 2: Delete runtime schema-creation execution from the shared runtime layer**

```python
# remove this path entirely
async def init_db(...):
    await conn.run_sync(self._base.metadata.create_all, ...)
```

Expected code change:
- no runtime code path should still call `metadata.create_all`

- [ ] **Step 3: Replace `init_db()` startup behavior with Alembic checks in each entrypoint**

```python
await ensure_database_at_head(service_name="admin-service", url=settings.DATABASE_URL)
```

Apply to:
- `backend_app/lifecycle.py`
- `admin_service/main.py`
- `testing_service/main.py`
- `admin_service/bootstrap_superadmin.py`

- [ ] **Step 4: Run focused tests to verify the new startup path**

Run:
```bash
uv --cache-dir /tmp/uv-cache run pytest tests/test_alembic_runtime.py tests/test_phase4_runtime.py tests/test_internal_contracts.py -q
```

Expected:
- PASS for new fail-fast checks
- PASS for “no init_db” assertions

- [ ] **Step 5: Commit the runtime cutover**

```bash
git add src/common/db/schema_version.py src/common/db/runtime.py src/common/db/__init__.py src/backend_app/lifecycle.py src/admin_service/main.py src/testing_service/main.py src/admin_service/bootstrap_superadmin.py tests/test_alembic_runtime.py tests/test_phase4_runtime.py tests/test_internal_contracts.py
git commit -m "refactor: enforce alembic-only runtime startup"
```

### Task 3: Remove Dead AUTO_INIT_DB Configuration And Align Tooling

**Files:**
- Modify: `src/common/config.py`
- Modify: `src/testing_service/config.py`
- Modify: `scripts/migrate.py`
- Modify: `scripts/bootstrap_service_databases.py`
- Modify: `tests/test_migration_structure.py`
- Modify: `tests/test_refactor_cleanup.py`

- [ ] **Step 1: Remove dead `AUTO_INIT_DB` configuration from runtime settings**

```python
# delete
AUTO_INIT_DB: bool = False

# delete wrappers like
def auto_init_db(self) -> bool: ...
```

- [ ] **Step 2: Keep migration scripts as the only schema advancement path**

```python
parser = argparse.ArgumentParser(
    description="Upgrade one or more service databases using service-local Alembic migrations"
)
```

Expected:
- `bootstrap_service_databases.py` remains canonical
- no script implies runtime auto-create behavior

- [ ] **Step 3: Update tests to assert config cleanup**

```python
def test_runtime_configs_do_not_expose_auto_init_db():
    common_config = (ROOT / "src" / "common" / "config.py").read_text(encoding="utf-8")
    assert "AUTO_INIT_DB" not in common_config
```

- [ ] **Step 4: Run the focused migration/config tests**

Run:
```bash
uv --cache-dir /tmp/uv-cache run pytest tests/test_migration_structure.py tests/test_refactor_cleanup.py tests/test_phase4_runtime.py -q
```

Expected:
- PASS with no `AUTO_INIT_DB` assumptions left

- [ ] **Step 5: Commit the config/tooling cleanup**

```bash
git add src/common/config.py src/testing_service/config.py scripts/migrate.py scripts/bootstrap_service_databases.py tests/test_migration_structure.py tests/test_refactor_cleanup.py tests/test_phase4_runtime.py
git commit -m "refactor: remove runtime auto-init configuration"
```

### Task 4: Align Docs And Historical Tests With Alembic-Only Truth

**Files:**
- Modify: `migrations/README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DATABASE.md`
- Modify: `docs/schema-ownership.md`
- Modify: `tests/test_review_fixes.py`
- Test: `tests/test_migration_structure.py`

- [ ] **Step 1: Remove any documentation that implies schema can be created at startup**

```md
Wrong: service startup may auto-create schema
Right: run `uv run migrate --service <svc> upgrade head` before service start
```

- [ ] **Step 2: Update historical tests that still encode the old assumption**

```python
assert "await init_db()" not in backend_lifecycle_source
assert "AUTO_INIT_DB" not in common_config_source
```

- [ ] **Step 3: Run doc/history cleanup tests**

Run:
```bash
uv --cache-dir /tmp/uv-cache run pytest tests/test_migration_structure.py tests/test_review_fixes.py -q
```

Expected:
- PASS with Alembic-only wording and assertions

- [ ] **Step 4: Commit the docs/history cleanup**

```bash
git add migrations/README.md docs/ARCHITECTURE.md docs/DATABASE.md docs/schema-ownership.md tests/test_review_fixes.py tests/test_migration_structure.py
git commit -m "docs: document alembic-only schema management"
```

### Task 5: Full Verification

**Files:**
- Verify-only: whole repository

- [ ] **Step 1: Run the complete test suite**

Run:
```bash
uv --cache-dir /tmp/uv-cache run pytest tests/ -v
```

Expected:
- PASS with 0 failures

- [ ] **Step 2: Confirm no runtime schema-creation path remains**

Run:
```bash
rg -n "init_db\\(|create_all|AUTO_INIT_DB|auto_init_db" src scripts docs tests
```

Expected:
- No active runtime startup path remains
- Remaining hits, if any, should only be intentional migration/documentation context that clearly states removal

- [ ] **Step 3: Commit the final verification checkpoint**

```bash
git add -A
git commit -m "test: verify alembic-only final cleanup"
```
