from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


BIG_UID = 9223372036854775807


def _build_user_management_test_client(monkeypatch, gateway: object) -> TestClient:
    from admin_service.api.v1.endpoints import user_management
    from admin_service.policies import require_active_admin

    app = FastAPI()
    app.dependency_overrides[require_active_admin] = lambda: object()
    app.include_router(user_management.router, prefix="/api/v1/admin")
    monkeypatch.setattr(user_management, "_gateway", gateway)
    return TestClient(app)


def test_user_management_public_schemas_serialize_uid_as_string():
    from admin_service.schemas.user_management import UserDetailData, UserListItem

    list_item = UserListItem(
        uid=BIG_UID,
        email="user@example.com",
        status=1,
        balance=100,
        created_at=datetime(2026, 4, 24, 12, 0, 0),
    )
    detail = UserDetailData(
        uid=BIG_UID,
        email="user@example.com",
        status=1,
        balance=100,
        frozen_amount=0,
        used_amount=0,
        total_requests=0,
        total_tokens=0,
        created_at=datetime(2026, 4, 24, 12, 0, 0),
        updated_at=datetime(2026, 4, 24, 12, 0, 0),
    )

    assert list_item.uid == str(BIG_UID)
    assert detail.uid == str(BIG_UID)
    assert f'"uid":"{BIG_UID}"' in list_item.model_dump_json()
    assert f'"uid":"{BIG_UID}"' in detail.model_dump_json()


def test_user_management_public_routes_serialize_uid_as_string(monkeypatch):
    now = datetime(2026, 4, 24, 12, 0, 0)

    class FakeGateway:
        async def list_users(self, **_kwargs) -> dict:
            return {
                "items": [
                    {
                        "uid": BIG_UID,
                        "email": "user@example.com",
                        "status": 1,
                        "balance": 100,
                        "created_at": now,
                    },
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
            }

        async def get_user_detail(self, uid: int) -> dict:
            assert uid == BIG_UID
            return {
                "uid": BIG_UID,
                "email": "user@example.com",
                "status": 1,
                "balance": 100,
                "frozen_amount": 0,
                "used_amount": 0,
                "total_requests": 0,
                "total_tokens": 0,
                "created_at": now,
                "updated_at": now,
            }

    client = _build_user_management_test_client(monkeypatch, FakeGateway())

    list_response = client.get("/api/v1/admin/users")
    detail_response = client.get(f"/api/v1/admin/users/{BIG_UID}")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["uid"] == str(BIG_UID)
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["uid"] == str(BIG_UID)


def test_user_management_gateway_maps_internal_404_to_not_found():
    from admin_service.gateway import UserManagementGateway
    from common.core.exceptions import NotFoundException
    from common.internal import InternalServiceResponseError

    gateway = UserManagementGateway()
    error = InternalServiceResponseError(
        "not found",
        target_service="user-service",
        path=f"/api/v1/internal/users/{BIG_UID}/detail",
        status_code=404,
        detail="User not found",
    )

    with pytest.raises(NotFoundException) as exc_info:
        gateway._handle_error(error)

    assert exc_info.value.status_code == 404


def test_user_management_detail_returns_404_for_missing_user(monkeypatch):
    from common.core.exceptions import NotFoundException

    class FakeGateway:
        async def get_user_detail(self, uid: int) -> dict:
            assert uid == BIG_UID
            raise NotFoundException("User not found")

    response = _build_user_management_test_client(
        monkeypatch,
        FakeGateway(),
    ).get(f"/api/v1/admin/users/{BIG_UID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
