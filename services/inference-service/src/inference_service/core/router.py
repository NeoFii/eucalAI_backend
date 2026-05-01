"""Central router aggregating all controllers."""

from fastapi import APIRouter

from inference_service.controllers.classify import router as classify_router

api_router = APIRouter()
api_router.include_router(classify_router)
