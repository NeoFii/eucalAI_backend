"""User-facing API key endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.dependencies import get_db_session
from user_service.models import User
from user_service.policies import require_active_user
from user_service.schemas import (
    ApiKeyCreateData,
    ApiKeyCreateRequest,
    ApiKeyItem,
    ApiKeyUpdateRequest,
    ApiResponse,
    AuthBaseResponse,
)
from user_service.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("", response_model=ApiResponse[list[ApiKeyItem]], summary="List my API keys")
async def list_keys(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    keys = await ApiKeyService.list(db, int(current_user.id))
    return {
        "code": 200,
        "message": "success",
        "data": [ApiKeyItem.model_validate(key) for key in keys],
    }


@router.post("", response_model=ApiResponse[ApiKeyCreateData], status_code=201, summary="Create API key")
async def create_key(
    payload: ApiKeyCreateRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    key, raw_key = await ApiKeyService.create(
        db,
        user_id=int(current_user.id),
        name=payload.name,
        quota_mode=payload.quota_mode,
        quota_limit=payload.quota_limit,
        allowed_models=payload.allowed_models,
        allow_ips=payload.allow_ips,
        expires_at=payload.expires_at,
    )
    return {
        "code": 201,
        "message": "created",
        "data": {
            "key": raw_key,
            "item": ApiKeyItem.model_validate(key),
        },
    }


@router.patch("/{key_id}", response_model=ApiResponse[ApiKeyItem], summary="Update API key")
async def update_key(
    key_id: int,
    payload: ApiKeyUpdateRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    key = await ApiKeyService.update(
        db,
        key_id=key_id,
        user_id=int(current_user.id),
        name=payload.name,
        new_quota_limit=payload.quota_limit,
        reset_quota_used=payload.reset_quota_used,
        allowed_models=payload.allowed_models,
        allow_ips=payload.allow_ips,
        expires_at=payload.expires_at,
        provided_fields=set(payload.model_fields_set),
    )
    return {
        "code": 200,
        "message": "success",
        "data": ApiKeyItem.model_validate(key),
    }


@router.post("/{key_id}/disable", response_model=AuthBaseResponse, summary="Disable API key")
async def disable_key(
    key_id: int,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> AuthBaseResponse:
    await ApiKeyService.disable(db, key_id=key_id, user_id=int(current_user.id))
    return AuthBaseResponse(code=200, message="success")


@router.delete("/{key_id}", response_model=AuthBaseResponse, summary="Delete API key")
async def delete_key(
    key_id: int,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> AuthBaseResponse:
    await ApiKeyService.delete(db, key_id=key_id, user_id=int(current_user.id))
    return AuthBaseResponse(code=200, message="deleted")
