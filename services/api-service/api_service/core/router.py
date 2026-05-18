"""API router registry — collects all versioned route groups."""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")

# Phase 4: User domain routes
# Phase 5: Admin domain routes
# Phase 7: Relay routes (mounted at app level, not under /api/v1)
# Phase 8: Internal routes
