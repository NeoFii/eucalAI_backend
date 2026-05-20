"""Tests for /health and /ready endpoints."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing app (settings validation needs them)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")
os.environ.setdefault("PROVIDER_SECRET_MASTER_KEY", "test-master-key-for-testing-only")

from app.main import app  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_returns_200(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "api-service"


async def test_health_includes_version(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "version" in body
    assert isinstance(body["version"], str)


async def test_ready_returns_200(client: AsyncClient):
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "api-service"
