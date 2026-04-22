from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from common.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
)

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"


def _user_internal_secret() -> str:
    from user_service.api.v1.endpoints import internal

    return internal.settings.INTERNAL_SECRET


def _admin_internal_secret() -> str:
    from admin_service.api.v1.endpoints import internal

    return internal.settings.INTERNAL_SECRET


class _ScalarResult:
    def __init__(self, *, scalar_one_or_none=None):
        self._scalar_one_or_none = scalar_one_or_none

    def scalar_one_or_none(self):
        return self._scalar_one_or_none


def _build_user_internal_app(fake_user):
    from user_service.api.v1.endpoints import internal
    from user_service.dependencies import get_db_session

    class FakeSession:
        async def execute(self, _statement):
            return _ScalarResult(scalar_one_or_none=fake_user)

    app = FastAPI()
    app.include_router(internal.router, prefix="/api/v1")

    async def _fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = _fake_db
    return app


def _build_admin_internal_app(fake_admin):
    from admin_service.api.v1.endpoints import internal
    from admin_service.dependencies import get_db_session

    class FakeSession:
        async def execute(self, _statement):
            return _ScalarResult(scalar_one_or_none=fake_admin)

    app = FastAPI()
    app.include_router(internal.router, prefix="/api/v1")

    async def _fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db_session] = _fake_db
    return app


def test_user_internal_endpoint_requires_signed_internal_request():
    from common.internal import build_internal_headers

    app = _build_user_internal_app(
        SimpleNamespace(id=5, uid=1001, email="user@example.com", status=1)
    )
    client = TestClient(app)

    forbidden = client.get(
        "/api/v1/internal/users/1001",
        headers={"X-Untrusted-Header": "wrong-secret"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Invalid internal secret"

    ok = client.get(
        "/api/v1/internal/users/1001",
        headers=build_internal_headers(
            secret=_user_internal_secret(),
            caller_service="router-service",
            method="GET",
            path="/api/v1/internal/users/1001",
        ),
    )
    assert ok.status_code == 200
    assert ok.json() == {
        "id": 5,
        "uid": 1001,
        "email": "user@example.com",
        "status": 1,
    }


def test_user_internal_endpoint_accepts_signed_internal_request():
    from common.internal import build_internal_headers

    app = _build_user_internal_app(
        SimpleNamespace(id=5, uid=1001, email="user@example.com", status=1)
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/internal/users/1001",
        headers=build_internal_headers(
            secret=_user_internal_secret(),
            caller_service="router-service",
            method="GET",
            path="/api/v1/internal/users/1001",
        ),
    )

    assert response.status_code == 200
    assert response.json()["uid"] == 1001


@pytest.mark.asyncio
async def test_user_internal_api_key_validation_endpoint_hashes_and_delegates(monkeypatch):
    from user_service.api.v1.endpoints.internal import (
        InternalApiKeyValidateRequest,
        validate_api_key,
    )
    from user_service.services.api_key_service import ApiKeyService

    captured = {}

    async def fake_validate(db, key_hash, *, model=None, client_ip=None):
        captured["call"] = {
            "db": db,
            "key_hash": key_hash,
            "model": model,
            "client_ip": client_ip,
        }
        return SimpleNamespace(id=9, user_id=5, name="default")

    monkeypatch.setattr(ApiKeyService, "validate_by_hash", fake_validate)

    fake_db = object()
    response = await validate_api_key(
        payload=InternalApiKeyValidateRequest(
            key="sk-test-123",
            model="gpt-4o-mini",
            client_ip="203.0.113.8",
        ),
        _=None,
        db=fake_db,
    )

    assert response.model_dump() == {"id": 9, "user_id": 5, "name": "default"}
    assert captured["call"] == {
        "db": fake_db,
        "key_hash": hashlib.sha256(b"sk-test-123").hexdigest(),
        "model": "gpt-4o-mini",
        "client_ip": "203.0.113.8",
    }


def test_user_internal_endpoint_rejects_untrusted_caller():
    from common.internal import build_internal_headers

    app = _build_user_internal_app(
        SimpleNamespace(id=5, uid=1001, email="user@example.com", status=1)
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/internal/users/1001",
            headers=build_internal_headers(
                secret=_user_internal_secret(),
                caller_service="backend-app",
                method="GET",
                path="/api/v1/internal/users/1001",
            ),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid internal caller"


@pytest.mark.asyncio
async def test_router_api_key_dependency_uses_user_internal_contract(monkeypatch):
    import json
    from starlette.requests import Request

    from router_service.dependencies import require_api_key

    captured = {}

    async def fake_validate_api_key(*, api_key, model=None, client_ip=None):
        captured["call"] = {
            "api_key": api_key,
            "model": model,
            "client_ip": client_ip,
        }
        return SimpleNamespace(id=7, user_id=5, name="default")

    monkeypatch.setattr(
        "router_service.dependencies.UserIdentityGateway.validate_api_key",
        fake_validate_api_key,
    )

    body = json.dumps(
        {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    ).encode("utf-8")
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-forwarded-for", b"203.0.113.8, 10.0.0.1"),
            ],
            "client": ("127.0.0.1", 12345),
        },
        receive,
    )

    principal = await require_api_key(request, authorization="Bearer sk-user-123")

    assert principal.id == 7
    assert principal.user_id == 5
    assert captured["call"] == {
        "api_key": "sk-user-123",
        "model": "gpt-4o-mini",
        "client_ip": "203.0.113.8",
    }
    assert request.state.api_key_principal.id == 7


@pytest.mark.asyncio
async def test_router_api_key_dependency_maps_invalid_key_to_401(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request
    from common.internal import InternalServiceResponseError
    from router_service.dependencies import require_api_key

    async def fake_validate_api_key(**_kwargs):
        raise InternalServiceResponseError(
            "user-service returned 404",
            target_service="user-service",
            path="/api/v1/internal/api-keys/validate",
            status_code=404,
            detail="API Key 不存在",
        )

    monkeypatch.setattr(
        "router_service.dependencies.UserIdentityGateway.validate_api_key",
        fake_validate_api_key,
    )

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/models",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        },
        receive,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(request, authorization="Bearer sk-invalid")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid api key"


def test_admin_internal_endpoint_requires_signed_internal_request():
    from common.internal import build_internal_headers

    app = _build_admin_internal_app(
        SimpleNamespace(
            id=7,
            uid=9001,
            email="admin@example.com",
            name="Admin",
            role="super_admin",
            status=1,
        )
    )
    client = TestClient(app)

    forbidden = client.get(
        "/api/v1/internal/admins/9001",
        headers={"X-Untrusted-Header": "wrong-secret"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Invalid internal secret"

    ok = client.get(
        "/api/v1/internal/admins/9001",
        headers=build_internal_headers(
            secret=_admin_internal_secret(),
            caller_service="user-service",
            method="GET",
            path="/api/v1/internal/admins/9001",
        ),
    )
    assert ok.status_code == 200
    assert ok.json() == {
        "id": 7,
        "uid": 9001,
        "email": "admin@example.com",
        "name": "Admin",
        "role": "super_admin",
        "status": 1,
    }


def test_signed_internal_request_rejects_expired_timestamp():
    from common.internal import _build_internal_signature

    app = _build_admin_internal_app(
        SimpleNamespace(
            id=7,
            uid=9001,
            email="admin@example.com",
            name="Admin",
            role="super_admin",
            status=1,
        )
    )
    client = TestClient(app)
    timestamp = "1"

    response = client.get(
        "/api/v1/internal/admins/9001",
        headers={
            "X-Internal-Service": "user-service",
            "X-Internal-Timestamp": timestamp,
            "X-Internal-Signature": _build_internal_signature(
                secret=_admin_internal_secret(),
                caller_service="user-service",
                method="GET",
                request_target="/api/v1/internal/admins/9001",
                timestamp=timestamp,
                canonical_body="",
            ),
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid internal secret"


def test_admin_internal_invitation_endpoints_require_secret_and_delegate(monkeypatch):
    from admin_service.api.v1.endpoints import internal
    from common.internal import build_internal_headers
    from admin_service.dependencies import get_db_session

    events = {}
    app = FastAPI()
    app.include_router(internal.router, prefix="/api/v1")

    async def _fake_db():
        yield object()

    async def fake_consume(db, code, used_by):
        events["consume"] = (db, code, used_by)

    async def fake_release(db, code, used_by):
        events["release"] = (db, code, used_by)
        return True

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.internal.InvitationCodeService.verify_and_use",
        fake_consume,
    )
    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.internal.InvitationCodeService.release",
        fake_release,
    )

    app.dependency_overrides[get_db_session] = _fake_db
    client = TestClient(app)

    forbidden = client.post(
        "/api/v1/internal/invitation-codes/consume",
        headers={"X-Untrusted-Header": "wrong-secret"},
        json={"code": "INVITE", "used_by_uid": 42},
    )
    assert forbidden.status_code == 403

    consume = client.post(
        "/api/v1/internal/invitation-codes/consume",
        headers=build_internal_headers(
            secret=_admin_internal_secret(),
            caller_service="user-service",
            method="POST",
            path="/api/v1/internal/invitation-codes/consume",
            json_body={"code": "INVITE", "used_by_uid": 42},
        ),
        json={"code": "INVITE", "used_by_uid": 42},
    )
    assert consume.status_code == 200
    assert consume.json() == {"consumed": True}
    assert events["consume"][1:] == ("INVITE", 42)

    release = client.post(
        "/api/v1/internal/invitation-codes/release",
        headers=build_internal_headers(
            secret=_admin_internal_secret(),
            caller_service="user-service",
            method="POST",
            path="/api/v1/internal/invitation-codes/release",
            json_body={"code": "INVITE", "used_by_uid": 42},
        ),
        json={"code": "INVITE", "used_by_uid": 42},
    )
    assert release.status_code == 200
    assert release.json() == {"released": True}
    assert events["release"][1:] == ("INVITE", 42)


def test_internal_request_signature_covers_query_string():
    from common.internal import build_internal_headers

    app = _build_admin_internal_app(
        SimpleNamespace(
            id=7,
            uid=9001,
            email="admin@example.com",
            name="Admin",
            role="super_admin",
            status=1,
        )
    )
    client = TestClient(app)

    valid = client.get(
        "/api/v1/internal/admins/9001?verbose=true",
        headers=build_internal_headers(
            secret=_admin_internal_secret(),
            caller_service="user-service",
            method="GET",
            path="/api/v1/internal/admins/9001",
            query_params={"verbose": "true"},
        ),
    )
    assert valid.status_code == 200

    tampered = client.get(
        "/api/v1/internal/admins/9001?verbose=false",
        headers=build_internal_headers(
            secret=_admin_internal_secret(),
            caller_service="user-service",
            method="GET",
            path="/api/v1/internal/admins/9001",
            query_params={"verbose": "true"},
        ),
    )
    assert tampered.status_code == 403
    assert tampered.json()["detail"] == "Invalid internal secret"


@pytest.mark.parametrize(
    ("exception_factory", "expected_status", "expected_detail"),
    [
        (lambda: InvalidInvitationCodeException("invalid"), 404, "invalid"),
        (lambda: InvitationCodeUsedException("used"), 409, "used"),
        (lambda: InvitationCodeDisabledException("disabled"), 403, "disabled"),
        (lambda: InvitationCodeExpiredException("expired"), 410, "expired"),
    ],
)
def test_admin_internal_invitation_consume_maps_domain_errors(monkeypatch, exception_factory, expected_status, expected_detail):
    from admin_service.api.v1.endpoints import internal
    from admin_service.dependencies import get_db_session
    from common.internal import build_internal_headers

    app = FastAPI()
    app.include_router(internal.router, prefix="/api/v1")

    async def _fake_db():
        yield object()

    async def fake_consume(_db, _code, _used_by):
        raise exception_factory()

    app.dependency_overrides[get_db_session] = _fake_db
    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.internal.InvitationCodeService.verify_and_use",
        fake_consume,
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/internal/invitation-codes/consume",
        headers=build_internal_headers(
            secret=_admin_internal_secret(),
            caller_service="user-service",
            method="POST",
            path="/api/v1/internal/invitation-codes/consume",
            json_body={"code": "INVITE", "used_by_uid": 42},
        ),
        json={"code": "INVITE", "used_by_uid": 42},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


@pytest.mark.asyncio
async def test_get_internal_json_allows_404(monkeypatch):
    from common import internal

    internal.reset_internal_circuit_breakers()

    class FakeResponse:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 should not raise when allow_404=True")

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json, params):
            assert method == "GET"
            assert url == "http://identity/api/v1/internal/users/1"
            assert headers["X-Internal-Service"] == "user-service"
            assert "X-Internal-Timestamp" in headers
            assert "X-Internal-Signature" in headers
            assert json is None
            assert params is None
            return FakeResponse()

    monkeypatch.setattr(internal.httpx, "AsyncClient", FakeClient)

    payload = await internal.get_internal_json(
        base_url="http://identity",
        target_service="user-service",
        path="/api/v1/internal/users/1",
        secret="secret",
        caller_service="user-service",
        timeout=3.0,
        allow_404=True,
    )

    assert payload is None


@pytest.mark.asyncio
async def test_post_internal_json_sends_json_body(monkeypatch):
    from common import internal

    internal.reset_internal_circuit_breakers()

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json, params):
            assert method == "POST"
            assert url == "http://identity/api/v1/internal/invitation-codes/consume"
            assert headers["X-Internal-Service"] == "user-service"
            assert "X-Internal-Timestamp" in headers
            assert "X-Internal-Signature" in headers
            assert json == {"code": "INVITE", "used_by_uid": 1}
            assert params is None
            return FakeResponse()

    monkeypatch.setattr(internal.httpx, "AsyncClient", FakeClient)

    payload = await internal.post_internal_json(
        base_url="http://identity",
        target_service="admin-service",
        path="/api/v1/internal/invitation-codes/consume",
        secret="secret",
        caller_service="user-service",
        timeout=3.0,
        json_body={"code": "INVITE", "used_by_uid": 1},
    )

    assert payload == {"ok": True}


@pytest.mark.asyncio
async def test_get_internal_json_raises_for_server_error(monkeypatch):
    from common import internal
    from common.internal import InternalServiceUnavailableError

    internal.reset_internal_circuit_breakers()

    request = httpx.Request("GET", "http://identity/api/v1/internal/users/1")

    class FakeResponse:
        status_code = 500

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "upstream failed",
                request=request,
                response=httpx.Response(500, request=request),
            )

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json, params):
            assert method == "GET"
            assert url == "http://identity/api/v1/internal/users/1"
            assert headers["X-Internal-Service"] == "router-service"
            assert "X-Internal-Timestamp" in headers
            assert "X-Internal-Signature" in headers
            assert json is None
            assert params is None
            return FakeResponse()

    monkeypatch.setattr(internal.httpx, "AsyncClient", FakeClient)

    with pytest.raises(InternalServiceUnavailableError) as exc_info:
        await internal.get_internal_json(
            base_url="http://identity",
            target_service="user-service",
            path="/api/v1/internal/users/1",
            secret="secret",
            caller_service="router-service",
            timeout=3.0,
        )
    assert exc_info.value.target_service == "user-service"


@pytest.mark.asyncio
async def test_get_internal_json_raises_response_error_for_client_error(monkeypatch):
    from common import internal
    from common.internal import InternalServiceResponseError

    internal.reset_internal_circuit_breakers()

    class FakeResponse:
        status_code = 409
        text = "conflict"

        def json(self):
            return {"detail": "Invitation code already used"}

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json, params):
            assert method == "GET"
            assert url == "http://identity/api/v1/internal/users/1"
            assert headers["X-Internal-Service"] == "router-service"
            assert json is None
            assert params is None
            return FakeResponse()

    monkeypatch.setattr(internal.httpx, "AsyncClient", FakeClient)

    with pytest.raises(InternalServiceResponseError) as exc_info:
        await internal.get_internal_json(
            base_url="http://identity",
            target_service="user-service",
            path="/api/v1/internal/users/1",
            secret="secret",
            caller_service="router-service",
            timeout=3.0,
        )

    assert exc_info.value.target_service == "user-service"
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Invitation code already used"


@pytest.mark.asyncio
async def test_build_internal_headers_propagates_request_id():
    from common.internal import build_internal_headers
    from common.observability import reset_request_id, set_request_id

    token = set_request_id("req-456")
    try:
        headers = build_internal_headers(
            secret="secret",
            caller_service="router-service",
            method="GET",
            path="/api/v1/internal/users/1",
        )
    finally:
        reset_request_id(token)

    assert headers["X-Request-ID"] == "req-456"
    assert headers["X-Internal-Service"] == "router-service"
    assert "X-Internal-Signature" in headers


@pytest.mark.asyncio
async def test_request_internal_json_retries_once_for_transport_error(monkeypatch):
    from common import internal

    internal.reset_internal_circuit_breakers()

    attempts = {"count": 0}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json, params):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise httpx.ConnectError("boom")
            assert headers["X-Internal-Service"] == "router-service"
            assert params is None
            return FakeResponse()

    async def fake_sleep(_delay):
        return None

    monkeypatch.setattr(internal.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(internal.asyncio, "sleep", fake_sleep)

    payload = await internal.get_internal_json(
        base_url="http://identity",
        target_service="user-service",
        path="/api/v1/internal/users/1",
        secret="secret",
        caller_service="router-service",
        timeout=3.0,
        max_retries=1,
        retry_backoff_seconds=0.01,
    )

    assert payload == {"ok": True}
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_request_internal_json_opens_circuit_after_threshold(monkeypatch):
    from common import internal
    from common.internal import InternalCircuitOpenError, InternalServiceUnavailableError

    internal.reset_internal_circuit_breakers()

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers, json, params):
            raise httpx.ConnectError("boom")

    async def fake_sleep(_delay):
        return None

    monkeypatch.setattr(internal.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(internal.asyncio, "sleep", fake_sleep)

    with pytest.raises(InternalServiceUnavailableError):
        await internal.get_internal_json(
            base_url="http://identity",
            target_service="user-service",
            path="/api/v1/internal/users/1",
            secret="secret",
            caller_service="router-service",
            timeout=3.0,
            max_retries=0,
            circuit_breaker_threshold=1,
            circuit_breaker_cooldown_seconds=60.0,
        )

    with pytest.raises(InternalCircuitOpenError):
        await internal.get_internal_json(
            base_url="http://identity",
            target_service="user-service",
            path="/api/v1/internal/users/1",
            secret="secret",
            caller_service="router-service",
            timeout=3.0,
            max_retries=0,
            circuit_breaker_threshold=1,
            circuit_breaker_cooldown_seconds=60.0,
        )


@pytest.mark.asyncio
async def test_router_user_identity_gateway_maps_payload(monkeypatch):
    from router_service.gateway import UserIdentityGateway
    from router_service.settings import RouterSettings

    monkeypatch.setattr(
        "router_service.dependencies._settings", RouterSettings.from_env()
    )

    captured = {}

    async def fake_post_internal_json(**kwargs):
        captured["call"] = kwargs
        return {
            "id": 17,
            "user_id": 23,
            "name": "router-key",
        }

    monkeypatch.setattr("router_service.gateway.post_internal_json", fake_post_internal_json)

    principal = await UserIdentityGateway.validate_api_key(
        api_key="sk-user-123",
        model="gpt-4o-mini",
        client_ip="203.0.113.8",
    )

    assert principal.id == 17
    assert principal.user_id == 23
    assert principal.name == "router-key"
    assert captured["call"]["target_service"] == "user-service"
    assert captured["call"]["path"] == "/api/v1/internal/api-keys/validate"
    assert captured["call"]["json_body"] == {
        "key": "sk-user-123",
        "model": "gpt-4o-mini",
        "client_ip": "203.0.113.8",
    }


@pytest.mark.asyncio
async def test_router_user_identity_gateway_maps_timeout(monkeypatch):
    from router_service.gateway import UserIdentityGateway
    from router_service.settings import RouterSettings
    from common.core.exceptions import ServiceUnavailableException

    monkeypatch.setattr(
        "router_service.dependencies._settings", RouterSettings.from_env()
    )

    async def fake_timeout(**_kwargs):
        raise ServiceUnavailableException("Identity service unavailable")

    monkeypatch.setattr("router_service.gateway.post_internal_json", fake_timeout)
    with pytest.raises(ServiceUnavailableException):
        await UserIdentityGateway.validate_api_key(api_key="sk-timeout")


@pytest.mark.asyncio
async def test_admin_invitation_client_maps_invitation_errors(monkeypatch):
    from user_service.gateway import AdminInvitationGateway

    request = httpx.Request("POST", "http://admin_service/api/v1/internal/invitation-codes/consume")

    async def fake_used(**_kwargs):
        response = httpx.Response(
            409,
            request=request,
            json={"message": "Invitation code already used"},
        )
        raise httpx.HTTPStatusError("conflict", request=request, response=response)

    monkeypatch.setattr("user_service.gateway.post_internal_json", fake_used)

    with pytest.raises(Exception) as exc_info:
        await AdminInvitationGateway().consume_invitation_code("INVITE", 1)

    assert exc_info.type.__name__ == "InvitationCodeUsedException"


@pytest.mark.asyncio
async def test_admin_invitation_client_maps_internal_response_errors(monkeypatch):
    from common.internal import InternalServiceResponseError
    from user_service.gateway import AdminInvitationGateway

    async def fake_used(**_kwargs):
        raise InternalServiceResponseError(
            "admin-service returned 409",
            target_service="admin-service",
            path="/api/v1/internal/invitation-codes/consume",
            status_code=409,
            detail="Invitation code already used",
        )

    monkeypatch.setattr("user_service.gateway.post_internal_json", fake_used)

    with pytest.raises(Exception) as exc_info:
        await AdminInvitationGateway().consume_invitation_code("INVITE", 1)

    assert exc_info.type.__name__ == "InvitationCodeUsedException"


@pytest.mark.asyncio
async def test_admin_invitation_client_release_returns_flag(monkeypatch):
    from user_service.gateway import AdminInvitationGateway

    async def fake_release(**_kwargs):
        return {"released": True}

    monkeypatch.setattr("user_service.gateway.post_internal_json", fake_release)

    released = await AdminInvitationGateway().release_invitation_code("INVITE", 1)
    assert released is True


def test_compose_and_dockerfile_include_router_without_removed_queue_runtime():
    repo_root = Path(__file__).resolve().parent.parent
    compose = (repo_root / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (repo_root / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    removed_worker = "testing" + "-worker"
    removed_queue_env = "BENCHMARK" + "_QUEUE_REDIS_URL"

    # Post-consolidation: admin/user live under backend-app.
    assert "backend-app:" in compose
    assert "router-service:" in compose
    assert removed_worker + ":" not in compose
    assert removed_queue_env not in compose
    # src/ layout: services are COPY'd from src/ into /app in the image.
    assert "src/router_service" in dockerfile
    assert "scripts" in dockerfile
    assert "EXPOSE 8000 8001 8003 8004" in dockerfile


def test_runtime_entrypoints_require_alembic_head_before_followup_work():
    repo_root = Path(__file__).resolve().parent.parent
    backend_main = (repo_root / "src" / "backend_app" / "main.py").read_text(encoding="utf-8")
    backend_lifecycle = (repo_root / "src" / "backend_app" / "lifecycle.py").read_text(
        encoding="utf-8"
    )
    admin_main = (repo_root / "src" / "admin_service" / "main.py").read_text(encoding="utf-8")
    bootstrap_cli = (
        repo_root / "src" / "admin_service" / "bootstrap_superadmin.py"
    ).read_text(encoding="utf-8")

    assert "lifespan=lifecycle_manager.lifespan" in backend_main
    assert "ensure_database_at_head" in backend_lifecycle
    assert 'service_name="admin-service"' in backend_lifecycle
    assert 'service_name="user-service"' in backend_lifecycle
    assert "AUTO_INIT_DB" not in backend_lifecycle
    assert 'ensure_database_at_head(service_name="admin-service"' in admin_main
    assert 'ensure_database_at_head(service_name="admin-service"' in bootstrap_cli
    assert "skip-init-db" not in bootstrap_cli
