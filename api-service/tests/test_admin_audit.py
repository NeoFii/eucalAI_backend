"""Tests for `controllers/admin/audit_logs.py` + ARQ cron registration.

Plan 05-02 / Task 3 behaviours covered:

- `test_meta_returns_shape`: `AdminAuditService.get_meta` returns the
  3-tuple (categories, action_labels, category_actions) and the
  controller serializes them into `AdminAuditLogMetaResponse`.
- `test_list_filters`: `list_logs` propagates filter kwargs into the
  service call.
- `test_audit_logs_router_mounted`: the audit logs router is mounted at
  `/api/v1/admin/audit-logs` and exposes the 3 documented endpoints.
- ARQ cron smoke checks: `run_health_checks` is callable, appears in the
  worker `functions` list, and the cron_jobs list contains a schedule
  for it. Source cadence (O-2): minute={0,10,20,30,40,50}.
- Pitfall 2 enforcement: `safe_audit_commit` is NOT referenced from this
  controller (grep is in the verify step, asserted here for documentation).
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long",
)
os.environ.setdefault(
    "INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long",
)

import pytest  # noqa: E402

from app.service.admin.audit_service import AdminAuditService  # noqa: E402


def test_audit_logs_router_mounted():
    """Router exposes /meta, /, /action-definitions/{code} (3 endpoints)."""
    from app.controller.admin.audit_logs import router

    paths = sorted({r.path for r in router.routes})
    # `/` shows as empty string in router-local form; we just assert the count
    # and confirm key paths exist (after admin_router prefix, paths become
    # /admin/audit-logs/* — covered by the next test).
    assert len(router.routes) >= 3


def test_audit_logs_router_mounted_under_admin():
    """admin_router contains all 3 audit-logs paths."""
    from app.controller.admin import admin_router

    paths = {r.path for r in admin_router.routes}
    assert "/admin/audit-logs" in paths
    assert "/admin/audit-logs/meta" in paths
    assert "/admin/audit-logs/action-definitions/{code}" in paths


@pytest.mark.asyncio
async def test_meta_returns_shape(mock_super_admin):
    """`AdminAuditService.get_meta` returns the 3-tuple expected by the controller."""
    # Service-level: stub out the cache + db.
    db = AsyncMock()

    # Patch _ensure_cache to avoid touching the DB.
    with patch.object(
        AdminAuditService, "_ensure_cache", new_callable=AsyncMock,
    ):
        # Inject the module-level cache state directly.
        import app.service.admin.audit_service as svc

        svc._category_actions_cache = {
            "auth": ("admin_login_success",),
            "user_management": ("topup_user",),
        }
        svc._action_labels_cache = {
            "admin_login_success": "登录成功",
            "topup_user": "用户充值",
        }
        categories, labels, cat_actions = await AdminAuditService.get_meta(db)

    assert set(categories) == {"auth", "user_management"}
    assert labels["admin_login_success"] == "登录成功"
    assert cat_actions["auth"] == ["admin_login_success"]


@pytest.mark.asyncio
async def test_list_filters(mock_super_admin):
    """`list_logs` forwards filter kwargs (category + actor_uid) to the repository."""
    db = AsyncMock()

    # Patch the AdminUserRepository.get_id_by_uid to short-circuit actor lookup.
    repo_mock = MagicMock()
    repo_mock.get_id_by_uid = AsyncMock(return_value=42)

    audit_repo_mock = MagicMock()
    audit_repo_mock.list_logs = AsyncMock(return_value=([], 0))

    with patch(
        "app.service.admin.audit_service.AdminUserRepository",
        return_value=repo_mock,
    ), patch(
        "app.service.admin.audit_service.AuditLogRepository",
        return_value=audit_repo_mock,
    ), patch.object(
        AdminAuditService, "_ensure_cache", new_callable=AsyncMock,
    ):
        # Seed the category-actions cache so the category filter resolves to
        # a known tuple of action codes.
        import app.service.admin.audit_service as svc

        svc._category_actions_cache = {"auth": ("admin_login_success",)}
        await AdminAuditService.list_logs(
            db,
            page=1,
            page_size=20,
            category="auth",
            actor_uid="adm_test01",
        )

    # The audit-log repo received the resolved actor_admin_id AND the action
    # tuple derived from the category filter.
    call_kwargs = audit_repo_mock.list_logs.call_args.kwargs
    assert call_kwargs["actor_admin_id"] == 42
    assert call_kwargs["actions"] == ("admin_login_success",)


# ---------------------------------------------------------------------------
# ARQ cron smoke checks (CONTEXT O-2 + O-5)
# ---------------------------------------------------------------------------


def test_run_health_checks_is_callable():
    """The ARQ job entry point exists and is callable."""
    from app.core.jobs import run_health_checks

    assert callable(run_health_checks)


def test_run_health_checks_registered_in_worker_settings():
    """`functions` list contains `run_health_checks` by name."""
    from app.core.jobs import get_worker_settings_kwargs

    kw = get_worker_settings_kwargs()
    names = [getattr(f, "__name__", "") for f in kw["functions"]]
    assert "run_health_checks" in names


def test_cron_schedule_matches_source_cadence():
    """O-2: cron schedule must be minute={0, 10, 20, 30, 40, 50}."""
    from app.core.jobs import get_worker_settings_kwargs

    kw = get_worker_settings_kwargs()
    cron_entries = kw.get("cron_jobs", [])

    # ARQ's `cron(func, ...)` returns a `CronJob` instance whose .name
    # contains the registered function name. The exact attribute shape can
    # vary across arq versions; this assertion is lenient (we look for any
    # cron entry whose serialized repr mentions `run_health_checks`).
    repr_list = [repr(c) for c in cron_entries]
    assert any("run_health_checks" in r for r in repr_list), repr_list

    # Source cadence is captured in the comment in core/jobs.py; smoke
    # check that minute={0,10,20,30,40,50} appears in at least one cron
    # entry's repr — covers the most common arq display formats.
    cadence_strings = [
        "0", "10", "20", "30", "40", "50",
    ]
    matched_entry = [r for r in repr_list if "run_health_checks" in r][0]
    # The repr of a CronJob in arq normally renders minute as a set/frozenset;
    # check that all 6 markers appear in the repr.
    for m in cadence_strings:
        assert m in matched_entry, f"cadence value {m} missing from {matched_entry}"


# ---------------------------------------------------------------------------
# HEALTH_CHECK_* settings + Pitfall 2 enforcement
# ---------------------------------------------------------------------------


def test_health_check_settings_present():
    """All 4 health-check settings are present with documented defaults."""
    from app.core.config import settings

    assert settings.HEALTH_CHECK_TIMEOUT_SECONDS == 15.0
    assert settings.HEALTH_CHECK_LLM_PROBE_ENABLED is True
    assert settings.HEALTH_CHECK_LLM_PROBE_MAX_TOKENS == 5
    assert settings.HEALTH_CHECK_RATE_LIMIT_DELAY == 0.5


def test_no_safe_audit_commit_in_audit_logs_controller():
    """Pitfall 2: the audit_logs controller must not USE safe_audit_commit.

    The docstring may mention the historical helper for context. We strip
    docstrings + comments before checking — only executable code should be
    scanned for the symbol.
    """
    import ast
    import inspect
    import re

    from app.controller.admin import audit_logs

    source = inspect.getsource(audit_logs)
    # Remove the module docstring + every # comment line, then check.
    tree = ast.parse(source)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        # Strip module docstring (its source span runs to end_lineno).
        doc_end = tree.body[0].end_lineno or 0
        lines = source.splitlines()
        source = "\n".join(lines[doc_end:])
    # Strip comments (best-effort, naive — sufficient here because the
    # controller has no string-literal `safe_audit_commit` references).
    cleaned = re.sub(r"#.*", "", source)
    assert "safe_audit_commit" not in cleaned
