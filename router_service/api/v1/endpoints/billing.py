"""Router usage and billing query endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from router_service.dependencies import RouterCurrentUser, get_current_user, get_db_session
from router_service.models import RouterBillingLedger, RouterUsageEvent
from router_service.schemas import (
    BillingLedgerItem,
    BillingLedgerResponse,
    BillingLedgerResponseData,
    UsageEventItem,
    UsageEventsResponse,
    UsageEventsResponseData,
    UsageSummaryData,
    UsageSummaryResponse,
)
router = APIRouter(tags=["router-billing"])


def _decimal_to_float(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.0


@router.get("/usage/events", response_model=UsageEventsResponse, summary="List router usage events")
async def list_usage_events(
    key_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UsageEventsResponse:
    filters = [RouterUsageEvent.owner_user_id == current_user.id]
    if key_id is not None:
        filters.append(RouterUsageEvent.router_api_key_id == key_id)

    stmt = (
        select(RouterUsageEvent)
        .where(*filters)
        .order_by(RouterUsageEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    total_stmt = select(func.count(RouterUsageEvent.id)).where(*filters)

    items = (await db.execute(stmt)).scalars().all()
    total = int((await db.execute(total_stmt)).scalar() or 0)
    return UsageEventsResponse(
        data=UsageEventsResponseData(
            items=[
                UsageEventItem(
                    id=int(item.id),
                    request_id=item.request_id,
                    router_api_key_id=item.router_api_key_id,
                    provider_slug=item.provider_slug,
                    requested_model=item.requested_model,
                    resolved_model=item.resolved_model,
                    prompt_tokens=item.prompt_tokens,
                    completion_tokens=item.completion_tokens,
                    total_tokens=item.total_tokens,
                    cost_input=_decimal_to_float(item.cost_input),
                    cost_output=_decimal_to_float(item.cost_output),
                    cost_total=_decimal_to_float(item.cost_total),
                    currency=item.currency,
                    status_code=item.status_code,
                    error_code=item.error_code,
                    error_message=item.error_message,
                    latency_ms=item.latency_ms,
                    created_at=item.created_at,
                )
                for item in items
            ],
            total=total,
        )
    )


@router.get("/usage/summary", response_model=UsageSummaryResponse, summary="Summarize router usage")
async def get_usage_summary(
    key_id: int | None = Query(default=None),
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UsageSummaryResponse:
    filters = [RouterUsageEvent.owner_user_id == current_user.id]
    if key_id is not None:
        filters.append(RouterUsageEvent.router_api_key_id == key_id)

    summary_stmt = select(
        func.count(RouterUsageEvent.id),
        func.coalesce(
            func.sum(
                case(
                    (
                        (RouterUsageEvent.status_code >= 200)
                        & (RouterUsageEvent.status_code < 300),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(func.sum(RouterUsageEvent.prompt_tokens), 0),
        func.coalesce(func.sum(RouterUsageEvent.completion_tokens), 0),
        func.coalesce(func.sum(RouterUsageEvent.total_tokens), 0),
        func.coalesce(func.sum(RouterUsageEvent.cost_total), 0),
    ).where(*filters)

    total_requests, success_requests, prompt_tokens, completion_tokens, total_tokens, total_cost = (
        (await db.execute(summary_stmt)).one()
    )
    return UsageSummaryResponse(
        data=UsageSummaryData(
            total_requests=int(total_requests or 0),
            success_requests=int(success_requests or 0),
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            total_tokens=int(total_tokens or 0),
            total_cost=float(total_cost or 0),
            currency="CNY",
        )
    )


@router.get("/billing/ledger", response_model=BillingLedgerResponse, summary="List router billing ledger")
async def list_billing_ledger(
    key_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: RouterCurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BillingLedgerResponse:
    filters = [RouterBillingLedger.owner_user_id == current_user.id]
    if key_id is not None:
        filters.append(RouterBillingLedger.router_api_key_id == key_id)

    stmt = (
        select(RouterBillingLedger)
        .where(*filters)
        .order_by(RouterBillingLedger.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    total_stmt = select(func.count(RouterBillingLedger.id)).where(*filters)

    items = (await db.execute(stmt)).scalars().all()
    total = int((await db.execute(total_stmt)).scalar() or 0)
    return BillingLedgerResponse(
        data=BillingLedgerResponseData(
            items=[
                BillingLedgerItem(
                    id=int(item.id),
                    usage_event_id=item.usage_event_id,
                    router_api_key_id=item.router_api_key_id,
                    direction=item.direction,
                    amount=_decimal_to_float(item.amount),
                    currency=item.currency,
                    balance_before=float(item.balance_before) if item.balance_before is not None else None,
                    balance_after=float(item.balance_after) if item.balance_after is not None else None,
                    description=item.description,
                    created_at=item.created_at,
                )
                for item in items
            ],
            total=total,
        )
    )
