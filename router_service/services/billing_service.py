"""Usage metering and billing logic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from router_service.config import get_settings
from router_service.models import RouterAPIKey, RouterBillingLedger, RouterUsageEvent
from router_service.services.auth_service import RouterKeyContext


class RouterQuotaExceededError(RuntimeError):
    """Raised when prepaid balance or quota is exhausted."""


PENDING_STATUS_CODE = 102
STALE_PENDING_STATUS_CODE = 504
STALE_PENDING_ERROR_CODE = "reservation_expired"
DEFAULT_RESERVED_COMPLETION_TOKENS = 1024
PROMPT_RESERVE_MULTIPLIER = 2


def _to_decimal(value: float | int | Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_cost(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@dataclass
class UsageReservation:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_input: Decimal
    cost_output: Decimal
    cost_total: Decimal


class RouterBillingService:
    """Calculate usage and persist usage/ledger rows."""

    @staticmethod
    async def _lock_router_key(
        db: AsyncSession,
        key_id: int,
        *,
        require_active: bool = True,
        include_deleted: bool = False,
    ) -> RouterAPIKey | None:
        stmt = select(RouterAPIKey).where(RouterAPIKey.id == key_id)
        if not include_deleted:
            stmt = stmt.where(RouterAPIKey.is_deleted.is_(False))
        stmt = stmt.with_for_update()
        key_row = (await db.execute(stmt)).scalar_one_or_none()
        if key_row is None:
            if require_active:
                raise RouterQuotaExceededError("Router API key is inactive")
            return None
        if require_active and not key_row.is_active:
            raise RouterQuotaExceededError("Router API key is inactive")
        return key_row

    @staticmethod
    async def _lock_usage_event(db: AsyncSession, request_id: str) -> RouterUsageEvent | None:
        stmt = select(RouterUsageEvent).where(RouterUsageEvent.request_id == request_id).with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        text = (text or "").strip()
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 4))

    @staticmethod
    def _extract_prompt_text(request_payload: dict[str, Any]) -> str:
        messages = request_payload.get("messages")
        if isinstance(messages, list):
            parts = []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(content)
            return "\n".join(parts)
        prompt = request_payload.get("prompt")
        if isinstance(prompt, list):
            return "\n".join(str(item) for item in prompt)
        return str(prompt or "")

    @staticmethod
    def _extract_completion_text(response_payload: dict[str, Any] | None) -> str:
        if not isinstance(response_payload, dict):
            return ""
        choices = response_payload.get("choices") or []
        parts = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                parts.append(message["content"])
            if isinstance(choice.get("text"), str):
                parts.append(choice["text"])
        return "\n".join(parts)

    @staticmethod
    def _extract_requested_completion_tokens(request_payload: dict[str, Any]) -> int:
        raw = request_payload.get("max_completion_tokens")
        if raw is None:
            raw = request_payload.get("max_tokens")
        try:
            requested = int(raw or 0)
        except (TypeError, ValueError):
            requested = 0
        return max(0, requested)

    @staticmethod
    def decide_usage(
        request_payload: dict[str, Any],
        response_payload: dict[str, Any] | None,
    ) -> tuple[int, int, int, str]:
        usage = response_payload.get("usage") if isinstance(response_payload, dict) else None
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
            return prompt_tokens, completion_tokens, total_tokens, "actual"

        prompt_tokens = RouterBillingService.estimate_tokens(
            RouterBillingService._extract_prompt_text(request_payload)
        )
        completion_tokens = RouterBillingService.estimate_tokens(
            RouterBillingService._extract_completion_text(response_payload)
        )
        total_tokens = prompt_tokens + completion_tokens
        return prompt_tokens, completion_tokens, total_tokens, "estimated" if total_tokens else "none"

    @staticmethod
    def calculate_cost(
        *,
        prompt_tokens: int,
        completion_tokens: int,
        input_price_per_m: float | None,
        output_price_per_m: float | None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        if input_price_per_m is None or output_price_per_m is None:
            return Decimal("0"), Decimal("0"), Decimal("0")
        input_cost = _to_cost(
            (_to_decimal(prompt_tokens) / Decimal("1000000")) * _to_decimal(input_price_per_m)
        )
        output_cost = _to_cost(
            (_to_decimal(completion_tokens) / Decimal("1000000")) * _to_decimal(output_price_per_m)
        )
        return input_cost, output_cost, _to_cost(input_cost + output_cost)

    @staticmethod
    def build_reservation(
        request_payload: dict[str, Any],
        *,
        input_price_per_m: float | None,
        output_price_per_m: float | None,
    ) -> UsageReservation:
        prompt_tokens = RouterBillingService.estimate_tokens(
            RouterBillingService._extract_prompt_text(request_payload)
        )
        requested_completion_tokens = RouterBillingService._extract_requested_completion_tokens(
            request_payload
        )
        choice_count = max(1, int(request_payload.get("n") or 1))
        reserved_prompt_tokens = max(1, prompt_tokens) * PROMPT_RESERVE_MULTIPLIER
        reserved_completion_tokens = requested_completion_tokens * choice_count
        if reserved_completion_tokens <= 0:
            reserved_completion_tokens = max(prompt_tokens, DEFAULT_RESERVED_COMPLETION_TOKENS)

        cost_input, cost_output, cost_total = RouterBillingService.calculate_cost(
            prompt_tokens=reserved_prompt_tokens,
            completion_tokens=reserved_completion_tokens,
            input_price_per_m=input_price_per_m,
            output_price_per_m=output_price_per_m,
        )
        return UsageReservation(
            prompt_tokens=reserved_prompt_tokens,
            completion_tokens=reserved_completion_tokens,
            total_tokens=reserved_prompt_tokens + reserved_completion_tokens,
            cost_input=cost_input,
            cost_output=cost_output,
            cost_total=cost_total,
        )

    @staticmethod
    async def preflight_guard(
        db: AsyncSession,
        context: RouterKeyContext,
        *,
        reserved_tokens: int = 0,
        reserved_cost: Decimal | None = None,
    ) -> None:
        key_row = await RouterBillingService._lock_router_key(db, context.key_id)

        billing_mode = (key_row.billing_mode or "postpaid").strip().lower()
        balance = _to_decimal(key_row.balance)
        rate_limit_rpm = key_row.rate_limit_rpm
        daily_quota_tokens = key_row.daily_quota_tokens
        monthly_quota_tokens = key_row.monthly_quota_tokens
        daily_quota_cost = _to_decimal(key_row.daily_quota_cost)
        monthly_quota_cost = _to_decimal(key_row.monthly_quota_cost)
        reserved_cost_decimal = _to_cost(_to_decimal(reserved_cost))

        if billing_mode == "prepaid":
            if balance <= 0:
                raise RouterQuotaExceededError("Prepaid balance exhausted")
            if reserved_cost_decimal > 0 and balance < reserved_cost_decimal:
                raise RouterQuotaExceededError("Prepaid balance exhausted")

        if rate_limit_rpm is not None:
            window_start = now() - timedelta(minutes=1)
            stmt = (
                select(func.count(RouterUsageEvent.id))
                .where(RouterUsageEvent.router_api_key_id == context.key_id)
                .where(RouterUsageEvent.created_at >= window_start)
            )
            used = int((await db.execute(stmt)).scalar() or 0)
            if used >= rate_limit_rpm:
                raise RouterQuotaExceededError("Rate limit exceeded")

        accounted_filter = or_(
            and_(RouterUsageEvent.status_code >= 200, RouterUsageEvent.status_code < 300),
            RouterUsageEvent.status_code == PENDING_STATUS_CODE,
        )
        current = now()
        day_start = datetime(current.year, current.month, current.day)
        month_start = datetime(current.year, current.month, 1)

        if daily_quota_tokens is not None:
            stmt = (
                select(func.coalesce(func.sum(RouterUsageEvent.total_tokens), 0))
                .where(RouterUsageEvent.router_api_key_id == context.key_id)
                .where(accounted_filter)
                .where(RouterUsageEvent.created_at >= day_start)
            )
            used = int((await db.execute(stmt)).scalar() or 0)
            if used + reserved_tokens > daily_quota_tokens:
                raise RouterQuotaExceededError("Daily token quota exceeded")

        if monthly_quota_tokens is not None:
            stmt = (
                select(func.coalesce(func.sum(RouterUsageEvent.total_tokens), 0))
                .where(RouterUsageEvent.router_api_key_id == context.key_id)
                .where(accounted_filter)
                .where(RouterUsageEvent.created_at >= month_start)
            )
            used = int((await db.execute(stmt)).scalar() or 0)
            if used + reserved_tokens > monthly_quota_tokens:
                raise RouterQuotaExceededError("Monthly token quota exceeded")

        if key_row.daily_quota_cost is not None:
            stmt = (
                select(func.coalesce(func.sum(RouterUsageEvent.cost_total), 0))
                .where(RouterUsageEvent.router_api_key_id == context.key_id)
                .where(accounted_filter)
                .where(RouterUsageEvent.created_at >= day_start)
            )
            used = _to_decimal((await db.execute(stmt)).scalar() or 0)
            if used + reserved_cost_decimal > daily_quota_cost:
                raise RouterQuotaExceededError("Daily cost quota exceeded")

        if key_row.monthly_quota_cost is not None:
            stmt = (
                select(func.coalesce(func.sum(RouterUsageEvent.cost_total), 0))
                .where(RouterUsageEvent.router_api_key_id == context.key_id)
                .where(accounted_filter)
                .where(RouterUsageEvent.created_at >= month_start)
            )
            used = _to_decimal((await db.execute(stmt)).scalar() or 0)
            if used + reserved_cost_decimal > monthly_quota_cost:
                raise RouterQuotaExceededError("Monthly cost quota exceeded")

    @staticmethod
    async def reserve_usage(
        db: AsyncSession,
        *,
        context: RouterKeyContext,
        request_id: str,
        endpoint: str,
        requested_model: str,
        resolved_model: str,
        request_payload: dict[str, Any],
        input_price_per_m: float | None,
        output_price_per_m: float | None,
    ) -> RouterUsageEvent:
        reservation = RouterBillingService.build_reservation(
            request_payload,
            input_price_per_m=input_price_per_m,
            output_price_per_m=output_price_per_m,
        )
        await RouterBillingService.preflight_guard(
            db,
            context,
            reserved_tokens=reservation.total_tokens,
            reserved_cost=reservation.cost_total,
        )

        currency = get_settings().ROUTER_BILLING_CURRENCY
        event = RouterUsageEvent(
            request_id=request_id,
            router_api_key_id=context.key_id,
            owner_user_id=context.owner_user_id,
            key_hash=context.key_hash,
            endpoint=endpoint,
            provider_slug=None,
            requested_model=requested_model,
            resolved_model=resolved_model,
            usage_source="reserved",
            prompt_tokens=reservation.prompt_tokens,
            completion_tokens=reservation.completion_tokens,
            total_tokens=reservation.total_tokens,
            input_price_per_m=_to_decimal(input_price_per_m) if input_price_per_m is not None else None,
            output_price_per_m=_to_decimal(output_price_per_m) if output_price_per_m is not None else None,
            cost_input=reservation.cost_input,
            cost_output=reservation.cost_output,
            cost_total=reservation.cost_total,
            currency=currency,
            status_code=PENDING_STATUS_CODE,
        )
        db.add(event)
        await db.flush()

        key_row = await RouterBillingService._lock_router_key(db, context.key_id)
        if (key_row.billing_mode or "postpaid") == "prepaid" and reservation.cost_total > 0:
            before = _to_decimal(key_row.balance)
            after = _to_cost(before - reservation.cost_total)
            key_row.balance = after
            db.add(
                RouterBillingLedger(
                    usage_event_id=event.id,
                    router_api_key_id=context.key_id,
                    owner_user_id=context.owner_user_id,
                    direction="debit",
                    amount=reservation.cost_total,
                    currency=currency,
                    balance_before=before,
                    balance_after=after,
                    description=f"reserve {endpoint} {resolved_model}",
                )
            )
            await db.flush()

        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def release_stale_reservations(
        db: AsyncSession,
        *,
        max_age_seconds: int,
    ) -> int:
        if max_age_seconds <= 0:
            return 0

        cutoff = now() - timedelta(seconds=max_age_seconds)
        stmt = (
            select(RouterUsageEvent)
            .where(RouterUsageEvent.status_code == PENDING_STATUS_CODE)
            .where(RouterUsageEvent.created_at < cutoff)
            .with_for_update()
        )
        stale_events = list((await db.execute(stmt)).scalars().all())
        if not stale_events:
            return 0

        currency = get_settings().ROUTER_BILLING_CURRENCY
        released = 0
        for event in stale_events:
            reserved_cost_total = _to_decimal(event.cost_total)
            event.usage_source = "none"
            event.prompt_tokens = 0
            event.completion_tokens = 0
            event.total_tokens = 0
            event.cost_input = Decimal("0")
            event.cost_output = Decimal("0")
            event.cost_total = Decimal("0")
            event.status_code = STALE_PENDING_STATUS_CODE
            event.error_code = STALE_PENDING_ERROR_CODE
            event.error_message = "Reserved usage event expired before settlement"
            event.latency_ms = None

            if event.router_api_key_id is not None and reserved_cost_total > 0:
                key_row = await RouterBillingService._lock_router_key(
                    db,
                    int(event.router_api_key_id),
                    require_active=False,
                    include_deleted=True,
                )
                if key_row is not None and (key_row.billing_mode or "postpaid") == "prepaid":
                    before = _to_decimal(key_row.balance)
                    after = _to_cost(before + reserved_cost_total)
                    key_row.balance = after
                    db.add(
                        RouterBillingLedger(
                            usage_event_id=event.id,
                            router_api_key_id=event.router_api_key_id,
                            owner_user_id=event.owner_user_id,
                            direction="credit",
                            amount=reserved_cost_total,
                            currency=currency,
                            balance_before=before,
                            balance_after=after,
                            description=f"expire {event.endpoint} {event.resolved_model}",
                        )
                    )
            released += 1

        await db.flush()
        return released

    @staticmethod
    async def settle_usage(
        db: AsyncSession,
        *,
        context: RouterKeyContext,
        request_id: str,
        endpoint: str,
        provider_slug: str | None,
        requested_model: str,
        resolved_model: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any] | None,
        input_price_per_m: float | None,
        output_price_per_m: float | None,
        status_code: int,
        latency_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> RouterUsageEvent:
        event = await RouterBillingService._lock_usage_event(db, request_id)
        if event is None:
            raise RuntimeError(f"Missing reserved usage event: {request_id}")

        reserved_cost_total = _to_decimal(event.cost_total)
        prompt_tokens, completion_tokens, total_tokens, usage_source = RouterBillingService.decide_usage(
            request_payload,
            response_payload,
        )
        cost_input, cost_output, cost_total = RouterBillingService.calculate_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_price_per_m=input_price_per_m,
            output_price_per_m=output_price_per_m,
        )
        if not (200 <= status_code < 300):
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            cost_input = Decimal("0")
            cost_output = Decimal("0")
            cost_total = Decimal("0")
            usage_source = "none"

        currency = get_settings().ROUTER_BILLING_CURRENCY
        event.endpoint = endpoint
        event.provider_slug = provider_slug
        event.requested_model = requested_model
        event.resolved_model = resolved_model
        event.usage_source = usage_source
        event.prompt_tokens = prompt_tokens
        event.completion_tokens = completion_tokens
        event.total_tokens = total_tokens
        event.input_price_per_m = _to_decimal(input_price_per_m) if input_price_per_m is not None else None
        event.output_price_per_m = _to_decimal(output_price_per_m) if output_price_per_m is not None else None
        event.cost_input = cost_input
        event.cost_output = cost_output
        event.cost_total = cost_total
        event.currency = currency
        event.status_code = status_code
        event.error_code = error_code
        event.error_message = error_message
        event.latency_ms = latency_ms
        await db.flush()

        key_row = await RouterBillingService._lock_router_key(db, context.key_id)
        if (key_row.billing_mode or "postpaid") == "prepaid":
            delta = _to_cost(cost_total - reserved_cost_total)
            if delta > 0:
                before = _to_decimal(key_row.balance)
                after = _to_cost(before - delta)
                key_row.balance = after
                db.add(
                    RouterBillingLedger(
                        usage_event_id=event.id,
                        router_api_key_id=context.key_id,
                        owner_user_id=context.owner_user_id,
                        direction="debit",
                        amount=delta,
                        currency=currency,
                        balance_before=before,
                        balance_after=after,
                        description=f"settle {endpoint} {resolved_model}",
                    )
                )
                await db.flush()
            elif delta < 0:
                refund = _to_cost(-delta)
                before = _to_decimal(key_row.balance)
                after = _to_cost(before + refund)
                key_row.balance = after
                db.add(
                    RouterBillingLedger(
                        usage_event_id=event.id,
                        router_api_key_id=context.key_id,
                        owner_user_id=context.owner_user_id,
                        direction="credit",
                        amount=refund,
                        currency=currency,
                        balance_before=before,
                        balance_after=after,
                        description=f"release {endpoint} {resolved_model}",
                    )
                )
                await db.flush()

        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def record_usage(
        db: AsyncSession,
        *,
        context: RouterKeyContext,
        request_id: str,
        endpoint: str,
        provider_slug: str | None,
        requested_model: str,
        resolved_model: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any] | None,
        input_price_per_m: float | None,
        output_price_per_m: float | None,
        status_code: int,
        latency_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> RouterUsageEvent:
        await RouterBillingService.reserve_usage(
            db,
            context=context,
            request_id=request_id,
            endpoint=endpoint,
            requested_model=requested_model,
            resolved_model=resolved_model,
            request_payload=request_payload,
            input_price_per_m=input_price_per_m,
            output_price_per_m=output_price_per_m,
        )
        return await RouterBillingService.settle_usage(
            db,
            context=context,
            request_id=request_id,
            endpoint=endpoint,
            provider_slug=provider_slug,
            requested_model=requested_model,
            resolved_model=resolved_model,
            request_payload=request_payload,
            response_payload=response_payload,
            input_price_per_m=input_price_per_m,
            output_price_per_m=output_price_per_m,
            status_code=status_code,
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=error_message,
        )
