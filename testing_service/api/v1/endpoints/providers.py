# -*- coding: utf-8 -*-
"""Testing service provider endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing_service.api.dependencies import (
    AdminPrincipal,
    get_current_admin,
    get_db_session,
)
from testing_service.provider_config import ProviderService
from testing_service.schemas import (
    ApiResponse,
    ListResponse,
    ProviderCreate,
    ProviderResponse,
    ProviderUpdate,
)

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get(
    "",
    response_model=ApiResponse[ListResponse[ProviderResponse]],
    summary="List providers",
)
async def list_providers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=200, description="Page size"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items_raw, total = await ProviderService.list_all(db, page, page_size)
    items = [ProviderResponse.model_validate(provider) for provider in items_raw]
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post(
    "",
    response_model=ApiResponse[ProviderResponse],
    status_code=201,
    summary="Create provider",
)
async def create_provider(
    data: ProviderCreate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        provider = await ProviderService.create(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "code": 201,
        "message": "created",
        "data": ProviderResponse.model_validate(provider),
    }


@router.put(
    "/{provider_id}",
    response_model=ApiResponse[ProviderResponse],
    summary="Update provider",
)
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    provider = await ProviderService.update(db, provider_id, data)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {
        "code": 200,
        "message": "success",
        "data": ProviderResponse.model_validate(provider),
    }


@router.delete(
    "/{provider_id}",
    response_model=ApiResponse[None],
    summary="Delete provider",
)
async def delete_provider(
    provider_id: int,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    ok, reason = await ProviderService.delete(db, provider_id)
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="Provider not found")
        raise HTTPException(status_code=400, detail=reason)
    return {"code": 200, "message": "deleted", "data": None}
