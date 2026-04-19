"""Backend-app structural tests.

The route-uniqueness gate is an aborting pre-condition for the whole
consolidation refactor: if any two sub-services share a (method, path) pair,
the merged app must not ship.
"""

from __future__ import annotations

from collections import Counter

import pytest
from fastapi.routing import APIRoute


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
    """All three domains' /internal/* sub-paths should be registered for
    inter-service HMAC calls (router -> backend-app)."""

    pairs = _build_app_routes_snapshot()
    paths_by_prefix = {path for _, path in pairs}

    # admin internal contracts — must stay under /api/v1/internal/ for HMAC callers
    assert any(p.startswith("/api/v1/internal/admins") for p in paths_by_prefix)
    assert any(p.startswith("/api/v1/internal/invitation-codes") for p in paths_by_prefix)
    # admin public routes are mounted under /api/v1/admin/ to avoid /auth collision
    assert any(p.startswith("/api/v1/admin/auth") for p in paths_by_prefix)
    # user public routes (public /api/v1/auth/* belongs to user)
    assert ("POST", "/api/v1/auth/login") in pairs
    # user internal contracts
    assert any(p.startswith("/api/v1/internal/users") for p in paths_by_prefix)
    # testing internal contracts (consumed by router-service)
    assert any(p.startswith("/api/v1/internal/router") for p in paths_by_prefix)


def test_backend_app_declares_health_and_ready_endpoints():
    pairs = _build_app_routes_snapshot()
    assert ("GET", "/health") in pairs
    assert ("GET", "/ready") in pairs


def test_backend_app_service_name_is_canonical():
    from backend_app.config import settings

    assert settings.SERVICE_NAME == "backend-app"
