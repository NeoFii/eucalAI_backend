"""Internal call log write endpoints (router-service only)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from controllers.internal import verify_router_only
from core.dependencies import get_db_session
from models.api_call_log import ApiCallLog
from schemas.internal_call_logs import (
    InternalBatchCallLogRequest,
    InternalCreateCallLogRequest,
    InternalUpdateCallLogRequest,
)
from services.balance_service import BalanceService
from services.usage_stat_service import UsageStatService

logger = logging.getLogger("user_service.internal.call_logs")

router = APIRouter(prefix="/internal", tags=["internal"])

_CALL_LOG_UPDATE_FIELDS = {
    "status", "selected_model", "provider_slug", "upstream_model",
    "config_version", "config_source", "inference_config_version",
    "inference_config_source", "routing_tier", "score_source",
    "total_score_0_10", "router_trace_id", "inference_error_code",
    "prompt_tokens", "completion_tokens", "cached_tokens", "total_tokens",
    "duration_ms", "upstream_latency_ms", "messages_count",
    "error_code", "error_msg", "cost", "provider_cost", "cost_detail",
    "routing_detail", "request_preview", "input_hash",
}

_CREATE_FIELDS = {
    "request_id", "user_id", "api_key_id", "model_name", "selected_model",
    "provider_slug", "upstream_model", "is_stream", "ip", "config_version",
    "config_source", "inference_config_version", "inference_config_source",
    "routing_tier", "score_source", "router_trace_id", "inference_error_code",
    "input_hash", "status",
}


@router.post("/call-logs", summary="Create API call log")
async def create_call_log(
    body: InternalCreateCallLogRequest,
    _: None = Depends(verify_router_only),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    existing = (
        await db.execute(
            select(ApiCallLog).where(ApiCallLog.request_id == body.request_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": int(existing.id), "request_id": existing.request_id}

    log = ApiCallLog(
        request_id=body.request_id,
        user_id=body.user_id,
        api_key_id=body.api_key_id,
        model_name=body.model_name,
        selected_model=body.selected_model,
        provider_slug=body.provider_slug,
        upstream_model=body.upstream_model,
        is_stream=body.is_stream,
        ip=body.ip,
        config_version=body.config_version,
        config_source=body.config_source,
        inference_config_version=body.inference_config_version,
        inference_config_source=body.inference_config_source,
        routing_tier=body.routing_tier,
        score_source=body.score_source,
        router_trace_id=body.router_trace_id,
        inference_error_code=body.inference_error_code,
        input_hash=body.input_hash,
        status=body.status,
        created_at=now(),
        updated_at=now(),
    )
    db.add(log)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(ApiCallLog).where(ApiCallLog.request_id == body.request_id)
            )
        ).scalar_one()
        return {"id": int(existing.id), "request_id": existing.request_id}
    await db.refresh(log)
    return {"id": int(log.id), "request_id": log.request_id}


@router.patch("/call-logs/{request_id}", summary="Update API call log")
async def update_call_log(
    request_id: str = Path(max_length=64),
    body: InternalUpdateCallLogRequest = ...,
    _: None = Depends(verify_router_only),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    log = (
        await db.execute(
            select(ApiCallLog).where(ApiCallLog.request_id == request_id)
        )
    ).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="call log not found")

    updates = body.model_dump(exclude_unset=True)
    if "error_msg" in updates and updates["error_msg"] is not None:
        updates["error_msg"] = updates["error_msg"][:512]

    for field_name, value in updates.items():
        if field_name in _CALL_LOG_UPDATE_FIELDS:
            setattr(log, field_name, value)
    log.updated_at = now()
    await db.commit()

    cost = updates.get("cost", 0) or 0
    final_status = updates.get("status")
    if cost > 0 and final_status == 1:
        total_tokens = updates.get("total_tokens", 0) or 0
        await BalanceService.consume_for_call_log(
            db,
            user_id=log.user_id,
            request_id=request_id,
            cost=cost,
            total_tokens=total_tokens,
            api_key_id=log.api_key_id,
        )
        await db.commit()

    final_status = updates.get("status")
    if final_status in (1, 2):
        await UsageStatService.upsert_from_log(db, log)
        await db.commit()

    return {"ok": True}


@router.post("/call-logs/batch", summary="Batch create/update call logs")
async def batch_call_logs(
    body: InternalBatchCallLogRequest,
    _: None = Depends(verify_router_only),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    created = 0
    updated = 0
    billed = 0
    finalized_logs: list[ApiCallLog] = []

    for entry in body.entries:
        request_id = entry.get("request_id")
        if not request_id:
            continue
        action = entry.get("action", "create")

        existing = (
            await db.execute(
                select(ApiCallLog).where(ApiCallLog.request_id == request_id)
            )
        ).scalar_one_or_none()

        if existing is None:
            create_fields = {k: v for k, v in entry.items() if k in _CREATE_FIELDS and v is not None}
            if "request_id" not in create_fields:
                create_fields["request_id"] = request_id
            log = ApiCallLog(**create_fields, created_at=now(), updated_at=now())
            db.add(log)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                existing = (
                    await db.execute(
                        select(ApiCallLog).where(ApiCallLog.request_id == request_id)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    continue
            else:
                created += 1
                if action != "complete":
                    continue
                existing = log

        update_fields = {k: v for k, v in entry.items() if k in _CALL_LOG_UPDATE_FIELDS and v is not None}
        if "error_msg" in update_fields and update_fields["error_msg"] is not None:
            update_fields["error_msg"] = str(update_fields["error_msg"])[:512]
        for field_name, value in update_fields.items():
            setattr(existing, field_name, value)
        existing.updated_at = now()
        updated += 1

        entry_status = entry.get("status")
        if entry_status in (1, 2):
            finalized_logs.append(existing)

        if action == "complete":
            cost = entry.get("cost", 0) or 0
            final_status = entry.get("status")
            if cost > 0 and final_status == 1:
                total_tokens = entry.get("total_tokens", 0) or 0
                success = await BalanceService.consume_for_call_log(
                    db,
                    user_id=existing.user_id,
                    request_id=request_id,
                    cost=cost,
                    total_tokens=total_tokens,
                    api_key_id=existing.api_key_id,
                )
                if success:
                    await db.flush()
                    billed += 1

    await db.commit()

    for log in finalized_logs:
        await UsageStatService.upsert_from_log(db, log)
    if finalized_logs:
        await db.commit()

    return {"ok": True, "created": created, "updated": updated, "billed": billed}
