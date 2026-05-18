"""API router registry — collects all versioned route groups."""

from __future__ import annotations

from fastapi import APIRouter

from api_service.controllers import auth, billing, keys

api_router = APIRouter(prefix="/api/v1")

# Phase 4: User domain routes
api_router.include_router(auth.router)     # Phase 4-01: 10 /auth/* endpoints
api_router.include_router(keys.router)     # Phase 4-02: 5 /keys endpoints (prefix in router)
api_router.include_router(billing.router)  # Phase 4-02: 8 /billing/* endpoints (prefix in router)
# Phase 4-03: model_catalog.router (mounted in next plan)
# Phase 5: Admin domain routes
# Phase 7: Relay routes (mounted at app level, not under /api/v1)
# Phase 8: Internal routes
