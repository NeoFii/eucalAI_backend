"""Admin route-monitor service — proxy elimination layer.

Replaces RouteMonitorGateway HTTP calls with direct CallLogRepository calls.
CLAUDE.md user identity rule: user_uid resolved to user_id internally.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.infra.db.query import ListParams
from app.common.utils.timezone import now
from app.repository.call_log_repository import CallLogRepository
from app.repository.user_repository import UserRepository


class AdminRouteMonitorService:
    """4 staticmethods composing CallLogRepository directly."""

    @staticmethod
    async def list_requests(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        user_uid: str | None = None,
        model_name: str | None = None,
        selected_model: str | None = None,
        provider_slug: str | None = None,
        routing_tier: int | None = None,
        status: int | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        request_id: str | None = None,
        input_hash: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list, int]:
        user_id: int | None = None
        if user_uid:
            user = await UserRepository(db).get_by_uid(user_uid)
            if user:
                user_id = int(user.id)
            else:
                return [], 0

        params = ListParams(
            page=page,
            page_size=page_size,
            time_field="created_at" if (start or end) else None,
            start=start,
            end=end,
        )

        repo = CallLogRepository(db)
        result = await repo.list_requests(
            params=params,
            user_id=user_id,
            model_name=model_name,
            selected_model=selected_model,
            provider_slug=provider_slug,
            routing_tier=routing_tier,
            status=status,
            score_min=score_min,
            score_max=score_max,
            request_id=request_id,
            input_hash=input_hash,
        )
        return result.items, result.total

    @staticmethod
    async def get_request_detail(db: AsyncSession, *, request_id: str):
        return await CallLogRepository(db).get_request_detail(request_id)

    @staticmethod
    async def get_aggregates(
        db: AsyncSession,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        user_uid: str | None = None,
        model_name: str | None = None,
        provider_slug: str | None = None,
    ) -> dict:
        user_id: int | None = None
        if user_uid:
            user = await UserRepository(db).get_by_uid(user_uid)
            if user:
                user_id = int(user.id)
            else:
                return {}

        current = now()
        effective_end = end or current
        effective_start = start or (effective_end - timedelta(days=7))

        return await CallLogRepository(db).aggregate_metrics(
            start=effective_start,
            end=effective_end,
            user_id=user_id,
            model_name=model_name,
            provider_slug=provider_slug,
        )

    @staticmethod
    async def get_compare(
        db: AsyncSession, *, request_id: str, limit: int = 20,
    ) -> dict:
        repo = CallLogRepository(db)
        target, siblings = await repo.find_same_input_siblings(
            request_id=request_id, limit=limit,
        )
        if target is None:
            return {"input_hash": None, "target": None, "siblings": []}
        input_hash = getattr(target, "input_hash", None)
        return {"input_hash": input_hash, "target": target, "siblings": siblings}


__all__ = ["AdminRouteMonitorService"]
