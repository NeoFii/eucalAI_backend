"""Public model catalog endpoints (proxied from admin-service)."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse

from gateways.model_catalog import model_catalog_gateway

router = APIRouter(tags=["model-catalog"])

_gateway = model_catalog_gateway


@router.get("/model-vendors", summary="List model vendors")
async def list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
):
    payload = await _gateway.list_vendors(page=page, page_size=page_size)
    return JSONResponse(content=payload)


@router.get("/models/categories", summary="List model categories")
async def list_model_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
):
    payload = await _gateway.list_categories(page=page, page_size=page_size)
    return JSONResponse(content=payload)


@router.get("/models", summary="List models")
async def list_models(
    category: str | None = None,
    vendors: str | None = Query(default=None, max_length=500),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    payload = await _gateway.list_models(
        category=category, vendors=vendors, q=q, page=page, page_size=page_size,
    )
    return JSONResponse(content=payload)


@router.get("/models/{slug}", summary="Get model detail")
async def get_model_detail(
    slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
):
    payload = await _gateway.get_model(slug)
    return JSONResponse(content=payload)
