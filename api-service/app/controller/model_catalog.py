"""Public model catalog endpoints.

Ported from ``services/user-service/src/controllers/model_catalog.py``. The
source forwarded every read to the admin domain via an out-of-process
gateway; here those calls become direct, in-process
``ModelCatalogReadService`` invocations (one fewer network hop per request).
Endpoint paths and behaviour stay identical so the front-end only needs to
change ``host:port``.

All four endpoints are public (no auth) — the same as in user-service.
"""
# ruff: noqa: B008

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.service.model_catalog_service import ModelCatalogReadService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["model-catalog"])


@router.get("/model-vendors", summary="List model vendors")
async def list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await ModelCatalogReadService.list_vendors(
            db, page=page, page_size=page_size,
        )
    except Exception:
        logger.exception("listModelVendorsFailed")
        raise
    return JSONResponse(content=payload)


@router.get("/models/categories", summary="List model categories")
async def list_model_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await ModelCatalogReadService.list_categories(
            db, page=page, page_size=page_size,
        )
    except Exception:
        logger.exception("listModelCategoriesFailed")
        raise
    return JSONResponse(content=payload)


@router.get("/models", summary="List supported models")
async def list_supported_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    vendors: list[str] | None = Query(None, alias="vendor"),
    q: str | None = Query(None, max_length=120),
    category: str | None = Query(None, max_length=120),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await ModelCatalogReadService.list_models(
            db,
            page=page,
            page_size=page_size,
            vendors=vendors,
            q=q,
            category=category,
        )
    except Exception:
        logger.exception("listSupportedModelsFailed")
        raise
    return JSONResponse(content=payload)


@router.get("/models/{slug}", summary="Get supported model by slug")
async def get_supported_model(
    slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await ModelCatalogReadService.get_model_by_slug(db, slug)
    except Exception:
        logger.exception("getSupportedModelFailed")
        raise
    return JSONResponse(content=payload)
