"""Relay controllers — aggregates all relay endpoint routers."""

from __future__ import annotations

from fastapi import APIRouter

from api_service.controllers.relay.chat import router as chat_router
from api_service.controllers.relay.anthropic import router as anthropic_router
from api_service.controllers.relay.responses import router as responses_router
from api_service.controllers.relay.models import router as models_router

relay_router = APIRouter(tags=["relay"])
relay_router.include_router(chat_router)
relay_router.include_router(anthropic_router)
relay_router.include_router(responses_router)
relay_router.include_router(models_router)

__all__ = ["relay_router"]
