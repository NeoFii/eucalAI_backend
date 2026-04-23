"""Backend-app structural tests.

The route-uniqueness gate is an aborting pre-condition for the whole
consolidation refactor: if any two sub-services share a (method, path) pair,
the merged app must not ship.
"""

from __future__ import annotations

import os
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!")
os.environ.setdefault("INTERNAL_SECRET", "test_internal_secret_32chars_long!")
os.environ.setdefault("ADMIN_DATABASE_URL", "mysql+aiomysql://root:pw@localhost/admin")
os.environ.setdefault("USER_DATABASE_URL", "mysql+aiomysql://root:pw@localhost/user")
os.environ.setdefault("PROVIDER_SECRET_MASTER_KEY", "a" * 64)


def _build_app_routes_snapshot():
    """Import backend_app.main.app (already instantiated at module level) and
    return the list of declared (method, path) pairs."""
    from backend_app.main import app

    pairs: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.append((method, route.path))
    return pairs


def test_route_uniqueness():
    """Every (method, path) registered on backend-app must be unique."""

    pairs = _build_app_routes_snapshot()
    counts = Counter(pairs)
    duplicates = {pair: count for pair, count in counts.items() if count > 1}
    assert not duplicates, (
        "backend-app has duplicate (method, path) routes, merging would shadow: "
        f"{duplicates}"
    )


def test_internal_endpoints_remain_reachable_under_backend_app():
    """Active /internal/* sub-paths stay registered for inter-service HMAC calls."""

    pairs = _build_app_routes_snapshot()
    paths_by_prefix = {path for _, path in pairs}

    # admin internal contracts — must stay under /api/v1/internal/ for HMAC callers
    assert any(p.startswith("/api/v1/internal/admins") for p in paths_by_prefix)
    # admin public routes are mounted under /api/v1/admin/ to avoid /auth collision
    assert any(p.startswith("/api/v1/admin/auth") for p in paths_by_prefix)
    # user public routes (public /api/v1/auth/* belongs to user)
    assert ("POST", "/api/v1/auth/login") in pairs
    assert ("GET", "/api/v1/billing/balance") in pairs
    assert ("POST", "/api/v1/billing/vouchers/redeem") in pairs
    assert ("GET", "/api/v1/billing/vouchers/redemptions") in pairs
    assert ("GET", "/api/v1/keys") in pairs
    assert ("POST", "/api/v1/admin/users/{uid}/topup") in pairs
    assert ("POST", "/api/v1/admin/vouchers") in pairs
    assert ("GET", "/api/v1/model-vendors") in pairs
    assert ("GET", "/api/v1/models/categories") in pairs
    assert ("GET", "/api/v1/models") in pairs
    assert ("GET", "/api/v1/models/{slug}") in pairs
    assert ("POST", "/api/v1/admin/model-catalog/models") in pairs
    # user internal contracts
    assert any(p.startswith("/api/v1/internal/users") for p in paths_by_prefix)


def test_removed_management_routes_are_not_registered_under_backend_app():
    pairs = _build_app_routes_snapshot()
    paths_by_prefix = {path for _, path in pairs}

    assert not any(p.startswith("/api/v1/benchmark") for p in paths_by_prefix)
    assert not any(p.startswith("/api/v1/model-providers") for p in paths_by_prefix)
    assert not any(p.startswith("/api/v1/providers") for p in paths_by_prefix)
    assert not any(p.startswith("/api/v1/vendors") for p in paths_by_prefix)
    assert not any(p.startswith("/api/v1/internal/router") for p in paths_by_prefix)


def test_backend_app_declares_health_and_ready_endpoints():
    pairs = _build_app_routes_snapshot()
    assert ("GET", "/health") in pairs
    assert ("GET", "/ready") in pairs


def test_backend_app_ready_endpoint_executes_all_database_probes(monkeypatch):
    from backend_app import main
    from backend_app import lifecycle as lifecycle_mod

    async def fake_check_database_ready(get_engine):
        return True, get_engine()

    async def fake_check_redis_ready():
        return True, None

    async def fake_init_redis(url):
        pass

    async def fake_close_redis():
        pass

    monkeypatch.setattr(main, "check_database_ready", fake_check_database_ready)
    monkeypatch.setattr(main, "check_redis_ready", fake_check_redis_ready)
    monkeypatch.setattr(main, "admin_db", SimpleNamespace(get_engine=lambda: "admin"))
    monkeypatch.setattr(main, "user_db", SimpleNamespace(get_engine=lambda: "user"))
    monkeypatch.setattr(lifecycle_mod, "init_redis", fake_init_redis)
    monkeypatch.setattr(lifecycle_mod, "close_redis", fake_close_redis)

    client = TestClient(main.app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "backend-app",
        "checks": {
            "database": {
                "status": "ok",
                "detail": {
                    "admin": {"ready": True, "error": "admin"},
                    "user": {"ready": True, "error": "user"},
                },
            },
            "redis": {
                "status": "ok",
                "detail": None,
            },
        },
    }


def test_backend_app_service_name_is_canonical():
    from backend_app.config import settings

    assert settings.SERVICE_NAME == "backend-app"


@pytest.mark.asyncio
async def test_lifecycle_manager_runs_startup_and_shutdown_in_registered_order():
    from fastapi import FastAPI

    from backend_app.lifecycle import LifecycleManager

    events = []
    manager = LifecycleManager()

    async def start_admin():
        events.append("start-admin")

    async def stop_admin():
        events.append("stop-admin")

    async def start_user():
        events.append("start-user")

    async def stop_user():
        events.append("stop-user")

    manager.register("admin", startup=start_admin, shutdown=stop_admin)
    manager.register("user", startup=start_user, shutdown=stop_user)

    async with manager.lifespan(FastAPI()):
        assert events == ["start-admin", "start-user"]

    assert events == ["start-admin", "start-user", "stop-user", "stop-admin"]


def test_backend_app_uses_lifecycle_manager_as_single_lifespan_path():
    from backend_app import main
    from backend_app.lifecycle import LifecycleManager

    def contains_lifecycle_manager(target, seen=None):
        seen = seen or set()
        target_id = id(target)
        if target_id in seen:
            return False
        seen.add(target_id)

        owner = getattr(target, "__self__", None)
        if owner is main.lifecycle_manager:
            return True

        closure = getattr(target, "__closure__", None) or ()
        for cell in closure:
            if contains_lifecycle_manager(cell.cell_contents, seen):
                return True
        return False

    assert isinstance(main.lifecycle_manager, LifecycleManager)
    assert contains_lifecycle_manager(main.app.router.lifespan_context)
    assert not hasattr(main, "lifespan")


def test_admin_route_completeness():
    """Every route declared in admin_service's standalone api_router must be
    reachable in backend-app (possibly under a shifted prefix)."""

    from admin_service.api.v1.router import api_router
    from fastapi.routing import APIRoute as _APIRoute

    # 1. Extract all (method, path) pairs from standalone admin api_router.
    standalone_pairs: list[tuple[str, str]] = []
    for route in api_router.routes:
        if not isinstance(route, _APIRoute):
            continue
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            standalone_pairs.append((method, route.path))

    assert standalone_pairs, "admin api_router should have routes"

    # 2. Categorise standalone routes.
    internal_pairs: list[tuple[str, str]] = []
    public_model_catalog_pairs: list[tuple[str, str]] = []
    admin_prefixed_pairs: list[tuple[str, str]] = []
    regular_admin_pairs: list[tuple[str, str]] = []

    # Public model-catalog paths (no prefix in model_catalog.py, mounted at /api/v1 in standalone)
    _public_mc_prefixes = ("/api/v1/model-vendors", "/api/v1/models")
    _admin_prefixed = ("/api/v1/admin/model-catalog", "/api/v1/admin/routing-config")

    for method, path in standalone_pairs:
        if "/internal/" in path:
            internal_pairs.append((method, path))
        elif any(path.startswith(p) for p in _admin_prefixed):
            admin_prefixed_pairs.append((method, path))
        elif any(path.startswith(p) for p in _public_mc_prefixes):
            public_model_catalog_pairs.append((method, path))
        else:
            regular_admin_pairs.append((method, path))

    # 3. Build the backend-app route set for comparison.
    backend_pairs = set(_build_app_routes_snapshot())

    missing: list[tuple[str, str, str]] = []

    # Regular admin paths: /api/v1/xxx -> /api/v1/admin/xxx
    for method, path in regular_admin_pairs:
        mapped = path.replace("/api/v1/", "/api/v1/admin/", 1)
        if (method, mapped) not in backend_pairs:
            missing.append((method, path, mapped))

    # Admin model-catalog / routing-config paths: already /api/v1/admin/*, keep as-is
    for method, path in admin_prefixed_pairs:
        if (method, path) not in backend_pairs:
            missing.append((method, path, path))

    # Internal paths: mounted at /api/v1/ in backend-app, same as standalone
    for method, path in internal_pairs:
        if (method, path) not in backend_pairs:
            missing.append((method, path, path))

    # Public model-catalog paths: mounted at /api/v1/ in backend-app, same as standalone
    for method, path in public_model_catalog_pairs:
        if (method, path) not in backend_pairs:
            missing.append((method, path, path))

    assert not missing, (
        "admin_service routes missing from backend-app "
        "(standalone_path -> expected_backend_path): "
        + ", ".join(f"{m} {orig} -> {mapped}" for m, orig, mapped in missing)
    )
