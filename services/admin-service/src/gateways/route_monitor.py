"""Admin -> router-service gateway for the route-monitor panel."""

from __future__ import annotations

from common.core.exceptions import NotFoundException, ValidationException
from common.gateway.base import BaseGateway
from core.config import settings

ROUTE_MONITOR_TIMEOUT_SECONDS = 8.0


class RouteMonitorGateway(BaseGateway):
    """HTTP gateway for route-monitor read endpoints in user-service."""

    def __init__(self) -> None:
        super().__init__(
            "user-service",
            base_url=settings.USER_SERVICE_URL,
            timeout=ROUTE_MONITOR_TIMEOUT_SECONDS,
            error_map={
                404: NotFoundException,
                400: ValidationException,
                422: ValidationException,
            },
        )

    async def list_requests(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
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
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        qp: dict = {"page": page, "page_size": page_size}
        if user_id is not None:
            qp["user_id"] = user_id
        if user_uid:
            qp["user_uid"] = user_uid
        if model_name:
            qp["model_name"] = model_name
        if selected_model:
            qp["selected_model"] = selected_model
        if provider_slug:
            qp["provider_slug"] = provider_slug
        if routing_tier is not None:
            qp["routing_tier"] = routing_tier
        if status is not None:
            qp["status"] = status
        if score_min is not None:
            qp["score_min"] = score_min
        if score_max is not None:
            qp["score_max"] = score_max
        if request_id:
            qp["request_id"] = request_id
        if input_hash:
            qp["input_hash"] = input_hash
        if start:
            qp["start"] = start
        if end:
            qp["end"] = end
        return await self._get(
            "/api/v1/internal/route-monitor/requests", query_params=qp,
        )

    async def get_request_detail(self, request_id: str) -> dict:
        return await self._get(
            f"/api/v1/internal/route-monitor/requests/{request_id}",
        )

    async def get_aggregates(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        user_id: int | None = None,
        user_uid: str | None = None,
        model_name: str | None = None,
        provider_slug: str | None = None,
    ) -> dict:
        qp: dict = {}
        if start:
            qp["start"] = start
        if end:
            qp["end"] = end
        if user_id is not None:
            qp["user_id"] = user_id
        if user_uid:
            qp["user_uid"] = user_uid
        if model_name:
            qp["model_name"] = model_name
        if provider_slug:
            qp["provider_slug"] = provider_slug
        return await self._get(
            "/api/v1/internal/route-monitor/aggregates", query_params=qp,
        )

    async def get_compare(self, request_id: str, *, limit: int = 20) -> dict:
        return await self._get(
            f"/api/v1/internal/route-monitor/compare/{request_id}",
            query_params={"limit": limit},
        )
