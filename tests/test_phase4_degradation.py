from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from common.core.exceptions import ServiceUnavailableException


@pytest.mark.asyncio
async def test_router_dependency_returns_503_when_identity_service_is_unavailable(monkeypatch):
    from router_service.dependencies import get_current_user

    monkeypatch.setattr(
        "router_service.dependencies.decode_token",
        lambda **_kwargs: {"uid": 77, "type": "access"},
    )

    async def fake_fetch_identity_user(_uid):
        raise ServiceUnavailableException("Identity service unavailable")

    monkeypatch.setattr(
        "router_service.dependencies.IdentityClientService.fetch_user_by_uid",
        fake_fetch_identity_user,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            request=None,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            access_token=None,
            db=object(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Identity service unavailable"


@pytest.mark.asyncio
async def test_content_admin_dependency_surfaces_admin_identity_outage(monkeypatch):
    from content_service.api.dependencies import get_current_admin

    monkeypatch.setattr(
        "content_service.api.dependencies.decode_token",
        lambda **_kwargs: {"uid": 42, "type": "access"},
    )

    async def fake_fetch_admin(_uid):
        raise ServiceUnavailableException("Admin identity service unavailable")

    monkeypatch.setattr(
        "content_service.api.dependencies.AdminIdentityClientService.fetch_admin_by_uid",
        fake_fetch_admin,
    )

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await get_current_admin(
            request=None,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            access_token=None,
            db=object(),
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_testing_admin_dependency_surfaces_admin_identity_outage(monkeypatch):
    from testing_service.api.dependencies import get_current_admin

    monkeypatch.setattr(
        "testing_service.api.dependencies.decode_token",
        lambda **_kwargs: {"uid": 42, "type": "access"},
    )

    async def fake_fetch_admin(_uid):
        raise ServiceUnavailableException("Admin identity service unavailable")

    monkeypatch.setattr(
        "testing_service.api.dependencies.AdminIdentityClientService.fetch_admin_by_uid",
        fake_fetch_admin,
    )

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await get_current_admin(
            request=None,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            access_token=None,
            db=object(),
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_admin_dashboard_stats_surfaces_user_identity_outage(monkeypatch):
    from admin_service.api.v1.endpoints.invitation import get_dashboard_stats

    async def fake_get_stats(_db):
        return {"total": 10, "used": 3, "valid": 7}

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.invitation.InvitationCodeService.get_stats",
        fake_get_stats,
    )

    async def fake_total_users():
        raise ServiceUnavailableException("User identity service unavailable")

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.invitation.IdentityClientService.fetch_total_users",
        fake_total_users,
    )

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await get_dashboard_stats(
            current_admin=SimpleNamespace(id=1, uid=99),
            db=object(),
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_router_routing_surfaces_testing_catalog_outage(monkeypatch):
    from router_service.services.routing_service import RoutingService

    async def fake_resolve_routes(**_kwargs):
        raise ServiceUnavailableException("Testing catalog service unavailable")

    monkeypatch.setattr(
        "router_service.services.routing_service.TestingCatalogClientService.resolve_routes",
        fake_resolve_routes,
    )

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await RoutingService.build_candidates(
            db=object(),
            model_name="demo-model",
        )

    assert exc_info.value.status_code == 503
