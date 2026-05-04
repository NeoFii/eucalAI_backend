"""Admin -> user-service gateway for the route-monitor panel."""

from __future__ import annotations

from typing import NoReturn

from common.core.exceptions import NotFoundException, ServiceUnavailableException, ValidationException
from common.gateway.base import BaseGateway
from common.internal import (
    InternalServiceError,
    InternalServiceResponseError,
    get_internal_json,
)
from core.config import settings

ROUTE_MONITOR_TIMEOUT_SECONDS = 8.0


class RouteMonitorGateway(BaseGateway):
    """HTTP gateway for route-monitor read endpoints in user-service."""

    def __init__(self) -> None:
        super().__init__(service_name="user-service")

    def _common_kwargs(self) -> dict:
        return {
            "base_url": settings.USER_SERVICE_URL,
            "target_service": self.service_name,
            "secret": settings.INTERNAL_SECRET,
            "caller_service": settings.SERVICE_NAME,
            "timeout": ROUTE_MONITOR_TIMEOUT_SECONDS,
            "max_retries": settings.INTERNAL_HTTP_MAX_RETRIES,
            "retry_backoff_seconds": settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
            "circuit_breaker_threshold": settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            "circuit_breaker_cooldown_seconds": (
                settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
            ),
        }

    def _handle_error(self, exc: InternalServiceError) -> NoReturn:
        if isinstance(exc, InternalServiceResponseError):
            if exc.status_code == 404:
                raise NotFoundException(detail=exc.detail or "Route request not found") from exc
            if exc.status_code in (400, 422):
                raise ValidationException(detail=exc.detail or "Validation error") from exc
        raise ServiceUnavailableException("User service unavailable") from exc

    async def list_requests(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
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
        try:
            return await get_internal_json(
                path="/api/v1/internal/route-monitor/requests",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_request_detail(self, request_id: str) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/route-monitor/requests/{request_id}",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_aggregates(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        user_id: int | None = None,
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
        if model_name:
            qp["model_name"] = model_name
        if provider_slug:
            qp["provider_slug"] = provider_slug
        try:
            return await get_internal_json(
                path="/api/v1/internal/route-monitor/aggregates",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_compare(self, request_id: str, *, limit: int = 20) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/route-monitor/compare/{request_id}",
                query_params={"limit": limit},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)
