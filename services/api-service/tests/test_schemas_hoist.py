"""Plan 05-01 — D-04 hoist + Pitfall 7/8 import-rewrite shape tests.

These tests cover both Task 1a (D-04 hoist) and Task 1b (HMAC sender + admin
exceptions + admin policies + 5 new settings keys).

Task 1a behaviors (1-4):
    1. `from api_service.common.schemas import ...` resolves; legacy
       `AuthBaseResponse` removed from `api_service.schemas.common`.
    2. `BaseResponse()` defaults to code=200/message="success"; `ErrorResponse()`
       defaults to code=400/message="error".
    3. `DateTimeModel.serialize_model` source contains the `list(data.items())`
       wrap (Pitfall 7 — runtime-safety preservation).
    4. `ApiResponse[T]` generic round-trips data.

Task 1b behaviors (5-9):
    5. HMAC sender exports resolve from `api_service.common.internal`.
    6. Signing primitives shared — receiver and sender both import them from
       `api_service.common.http.internal_signing` (no duplicate function
       bodies).
    7. `AdminConflictException` (409) and `AdminPermissionDeniedException`
       (403) exist in `api_service.common.core.exceptions`.
    8. `require_active_admin` and `require_super_admin` are coroutine
       functions in `api_service.core.policies`.
    9. Five new settings keys exist on `ApiServiceSettings` with documented
       defaults.
"""

from __future__ import annotations

import inspect

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Task 1a: D-04 hoist + Phase 4 import rewrite
# ──────────────────────────────────────────────────────────────────────────────


def test_phase4_imports_rewritten() -> None:
    """Behavior 1 — new path resolves; legacy alias removed (Pitfall 8)."""
    from api_service.common.schemas import (
        ApiResponse,
        BaseResponse,
        DateTimeModel,
        ErrorResponse,
    )

    assert BaseResponse is not None
    assert ErrorResponse is not None
    assert DateTimeModel is not None
    assert ApiResponse is not None

    # Legacy aliases must be erased — importing them must fail.
    with pytest.raises(ImportError):
        from api_service.schemas.common import AuthBaseResponse  # noqa: F401


def test_baseresponse_defaults() -> None:
    """Behavior 2 — BaseResponse / ErrorResponse default values."""
    from api_service.common.schemas import BaseResponse, ErrorResponse

    base = BaseResponse()
    assert base.code == 200
    assert base.message == "success"

    err = ErrorResponse()
    assert err.code == 400
    assert err.message == "error"


def test_datetime_model_uses_list_wrap() -> None:
    """Behavior 3 — runtime-safety: the `list(data.items())` wrap is preserved."""
    import api_service.common.schemas as schemas_mod

    source = inspect.getsource(schemas_mod)
    assert "list(data.items())" in source, (
        "DateTimeModel.serialize_model must iterate over list(data.items()) "
        "to avoid mutating the dict while iterating (Pitfall 7)."
    )


def test_apiresponse_generic() -> None:
    """Behavior 4 — ApiResponse[T] round-trips the data payload."""
    from api_service.common.schemas import ApiResponse

    resp = ApiResponse[int](code=200, message="ok", data=42)
    assert resp.data == 42


# ──────────────────────────────────────────────────────────────────────────────
# Task 1b: HMAC sender + admin exceptions + admin policies + settings
# ──────────────────────────────────────────────────────────────────────────────


def test_internal_sender_imports_resolve() -> None:
    """Behavior 5 — HMAC sender exports importable from `api_service.common.internal`."""
    from api_service.common.internal import (  # noqa: F401
        InternalCircuitOpenError,
        InternalServiceError,
        InternalServiceResponseError,
        InternalServiceUnavailableError,
        close_internal_clients,
        get_internal_client,
        get_internal_json,
        request_internal_json,
        reset_internal_circuit_breakers,
    )


def test_signing_primitives_shared() -> None:
    """Behavior 6 — signing primitives live in a single module.

    Both the receiver (`common/http/internal_auth.py`) and the sender
    (`common/internal.py`) must import `_build_internal_signature` from the
    shared `common/http/internal_signing.py` module. Neither should define
    the function locally.
    """
    from api_service.common.http import internal_auth, internal_signing
    from api_service.common import internal as internal_sender

    # The shared module must define the primitive.
    shared_src = inspect.getsource(internal_signing)
    assert "def _build_internal_signature" in shared_src, (
        "internal_signing.py must define `_build_internal_signature` (single source)."
    )

    # Receiver must not redefine the primitive.
    receiver_src = inspect.getsource(internal_auth)
    assert "def _build_internal_signature" not in receiver_src, (
        "common/http/internal_auth.py must import `_build_internal_signature` "
        "from common/http/internal_signing.py — local definition is a dedupe failure."
    )

    # Sender must not redefine the primitive either.
    sender_src = inspect.getsource(internal_sender)
    assert "def _build_internal_signature" not in sender_src, (
        "common/internal.py must import `_build_internal_signature` from "
        "common/http/internal_signing.py — local definition is a dedupe failure."
    )


def test_admin_exceptions_present() -> None:
    """Behavior 7 — AdminConflictException (409), AdminPermissionDeniedException (403)."""
    from api_service.common.core.exceptions import (
        AdminConflictException,
        AdminPermissionDeniedException,
    )

    conflict = AdminConflictException()
    denied = AdminPermissionDeniedException()
    assert conflict.status_code == 409, (
        f"AdminConflictException.status_code must be 409, got {conflict.status_code}"
    )
    assert denied.status_code == 403, (
        f"AdminPermissionDeniedException.status_code must be 403, got {denied.status_code}"
    )


def test_admin_policies_callable() -> None:
    """Behavior 8 — require_active_admin and require_super_admin are coroutines."""
    from api_service.core.policies import require_active_admin, require_super_admin

    assert inspect.iscoroutinefunction(require_active_admin), (
        "require_active_admin must be an async function."
    )
    assert inspect.iscoroutinefunction(require_super_admin), (
        "require_super_admin must be an async function."
    )


def test_settings_new_keys() -> None:
    """Behavior 9 — five new settings keys with documented defaults."""
    from api_service.core.config import settings

    assert settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP is True
    assert settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS is False
    assert settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS is False
    assert settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD == 5
    assert settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS == 30
