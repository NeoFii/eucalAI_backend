"""Router-owned user API key management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from router_service.dependencies import RouterCurrentUser, get_current_user, get_db_session
from router_service.schemas import (
    RouterApiKeyCreateRequest,
    RouterApiKeyCreateResponse,
    RouterApiKeyDeleteResponse,
    RouterApiKeyDeleteResponseData,
    RouterApiKeyItem,
    RouterApiKeyListResponse,
    RouterApiKeyListResponseData,
    RouterApiKeyRevealResponse,
    RouterApiKeyUpdateRequest,
    RouterApiKeyUpdateResponse,
)
from router_service.services import RouterKeyAuthService

router = APIRouter(prefix="/keys", tags=["router-keys"])


def _to_item(payload: dict) -> RouterApiKeyItem:
    return RouterApiKeyItem(**payload)


@router.get("", response_model=RouterApiKeyListResponse, summary="List router API keys")
async def list_router_keys(
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> RouterApiKeyListResponse:
    items = await RouterKeyAuthService.list_keys(db, owner_user_id=current_user.id)
    return RouterApiKeyListResponse(
        data=RouterApiKeyListResponseData(items=[_to_item(item) for item in items]),
    )


@router.post(
    "",
    response_model=RouterApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create router API key",
)
async def create_router_key(
    request: RouterApiKeyCreateRequest,
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> RouterApiKeyCreateResponse:
    payload = await RouterKeyAuthService.create_key(
        db,
        owner_user_id=current_user.id,
        name=request.name,
    )
    item_payload = dict(payload)
    api_key = item_payload.pop("api_key")
    return RouterApiKeyCreateResponse(
        code=201,
        message="created",
        data={
            "item": _to_item(item_payload),
            "api_key": api_key,
        },
    )


@router.patch("/{key_id}", response_model=RouterApiKeyUpdateResponse, summary="Update router API key")
async def update_router_key(
    key_id: int,
    request: RouterApiKeyUpdateRequest,
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> RouterApiKeyUpdateResponse:
    payload = await RouterKeyAuthService.update_owned_key(
        db,
        owner_user_id=current_user.id,
        key_id=key_id,
        name=request.name,
        is_active=request.is_active,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Router API key not found")
    return RouterApiKeyUpdateResponse(data=_to_item(payload))


@router.post("/{key_id}/reveal", response_model=RouterApiKeyRevealResponse, summary="Reveal router API key")
async def reveal_router_key(
    key_id: int,
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> RouterApiKeyRevealResponse:
    try:
        payload = await RouterKeyAuthService.reveal_owned_key(
            db,
            owner_user_id=current_user.id,
            key_id=key_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="Router API key not found")
    item_payload = dict(payload)
    api_key = item_payload.pop("api_key")
    return RouterApiKeyRevealResponse(
        data={
            "item": _to_item(item_payload),
            "api_key": api_key,
        },
    )


@router.delete("/{key_id}", response_model=RouterApiKeyDeleteResponse, summary="Delete router API key")
async def delete_router_key(
    key_id: int,
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> RouterApiKeyDeleteResponse:
    deleted = await RouterKeyAuthService.delete_owned_key(
        db,
        owner_user_id=current_user.id,
        key_id=key_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Router API key not found")
    return RouterApiKeyDeleteResponse(
        data=RouterApiKeyDeleteResponseData(deleted=True),
    )
