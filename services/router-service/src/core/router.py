"""Central router aggregating all controllers."""

from fastapi import APIRouter

from controllers.chat import router as chat_router
from controllers.messages import router as messages_router
from controllers.meta import router as meta_router
from controllers.responses import router as responses_router

api_router = APIRouter()
api_router.include_router(meta_router)
api_router.include_router(chat_router)
api_router.include_router(messages_router)
api_router.include_router(responses_router)
