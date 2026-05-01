"""Central router aggregating all controllers."""

from fastapi import APIRouter

from controllers.meta import router as meta_router
from controllers.chat import router as chat_router
from controllers.completions import router as completions_router

api_router = APIRouter()
api_router.include_router(meta_router)
api_router.include_router(chat_router)
api_router.include_router(completions_router)
