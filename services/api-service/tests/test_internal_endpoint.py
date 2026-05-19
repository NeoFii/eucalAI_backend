"""Tests for the internal HMAC-protected endpoint (Phase 8-01 / Task 2).

Verifies:
- 403 when no HMAC headers are provided
- 200 with valid HMAC signature from inference-service
- Response body contains all InternalRoutingConfigInference fields
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import os
import time
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from api_service.common.http.internal_signing import (  # noqa: E402
    INTERNAL_CALLER_HEADER,
    INTERNAL_SIGNATURE_HEADER,
    INTERNAL_TIMESTAMP_HEADER,
    _build_internal_signature,
    _canonicalize_request_body,
    _canonicalize_request_target,
)
from api_service.core.config import settings  # noqa: E402


def _make_hmac_headers(
    method: str,
    path: str,
    caller: str = "inference-service",
    body: bytes = b"",
) -> dict[str, str]:
    """Generate valid HMAC headers for testing."""
    timestamp = str(int(time.time()))
    canonical_body = _canonicalize_request_body(body)
    request_target = _canonicalize_request_target(path)
    signature = _build_internal_signature(
        secret=settings.INTERNAL_SECRET,
        caller_service=caller,
        method=method,
        request_target=request_target,
        timestamp=timestamp,
        canonical_body=canonical_body,
    )
    return {
        INTERNAL_CALLER_HEADER: caller,
        INTERNAL_TIMESTAMP_HEADER: timestamp,
        INTERNAL_SIGNATURE_HEADER: signature,
    }


ENDPOINT_PATH = "/api/v1/internal/routing-config/active/inference"

MOCK_RESOLVE_RESULT = {
    "router_alias": "auto",
    "user_facing_aliases": ["auto"],
    "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
    "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
    "score_bands": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
    "tier_model_map": {"1": "gpt-4o", "2": "gpt-4o-mini", "3": "gpt-4o", "4": "gpt-4o", "5": "gpt-4o"},
    "default_user_rpm": 20,
    "system_rpm_cap": 1000,
}


@pytest.fixture
def mock_db_session():
    """Patch get_db to yield an AsyncMock session."""
    session = AsyncMock()

    async def _override():
        yield session

    return _override, session


@pytest.fixture
def app_client(mock_db_session):
    """Create an HTTPX AsyncClient with the FastAPI app, DB dependency overridden."""
    from api_service.core.db import get_db
    from api_service.main import app

    override_gen, _ = mock_db_session
    app.dependency_overrides[get_db] = override_gen
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_returns_403_without_hmac_headers(app_client):
    """Endpoint returns 403 when no HMAC headers are provided."""
    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get(ENDPOINT_PATH)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_returns_403_with_wrong_caller(app_client):
    """Endpoint returns 403 when caller is not inference-service."""
    headers = _make_hmac_headers("GET", ENDPOINT_PATH, caller="wrong-service")
    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get(ENDPOINT_PATH, headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_returns_200_with_valid_hmac(app_client):
    """Endpoint returns 200 with valid HMAC from inference-service."""
    headers = _make_hmac_headers("GET", ENDPOINT_PATH)

    with patch(
        "api_service.controllers.internal.RoutingSettingService.resolve_for_internal",
        new_callable=AsyncMock,
        return_value=MOCK_RESOLVE_RESULT,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            response = await client.get(ENDPOINT_PATH, headers=headers)

    assert response.status_code == 200
    data = response.json()
    # Verify all 6 InternalRoutingConfigInference fields
    assert data["version"] == 0
    assert data["status"] == "active"
    assert data["route_order"] == ["纠错", "工具调用", "通用任务", "任务拆解", "编程"]
    assert data["weights"]["纠错"] == 1.0
    assert data["score_bands"] == "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1"
    assert data["tier_model_map"]["1"] == "gpt-4o"
