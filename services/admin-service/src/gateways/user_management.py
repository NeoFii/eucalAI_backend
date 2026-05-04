"""Admin control-plane facade for user-service.

This module proxies user-management and voucher operations to user-service
via HMAC-signed internal HTTP calls. It is intentionally part of admin_service
(not a separate package) because admin is the only consumer of these facades.
If the admin-service package boundary needs tightening, this module and the
corresponding endpoint files (user_management.py, vouchers.py) are the
candidates for extraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NoReturn

from core.config import settings
from core.exceptions import AdminConflictException, AdminPermissionDeniedException
from common.core.exceptions import (
    NotFoundException,
    ServiceUnavailableException,
    ValidationException,
)
from common.gateway.base import BaseGateway
from common.internal import (
    InternalServiceError,
    InternalServiceResponseError,
    get_internal_json,
    post_internal_json,
    request_internal_json,
)
from common.utils.timezone import format_iso

IDENTITY_TIMEOUT_SECONDS = 3.0


class UserStatsGatewayInterface(ABC):
    """Contract for user-service statistics needed by admin-service."""

    @abstractmethod
    async def fetch_total_users(self) -> int:
        """Return the total user count."""


class UserStatsGateway(BaseGateway, UserStatsGatewayInterface):
    """HTTP gateway for user-service statistics."""

    def __init__(self) -> None:
        super().__init__(service_name="user-service")

    def _common_kwargs(self) -> dict:
        return {
            "base_url": settings.USER_SERVICE_URL,
            "target_service": self.service_name,
            "secret": settings.INTERNAL_SECRET,
            "caller_service": settings.SERVICE_NAME,
            "timeout": IDENTITY_TIMEOUT_SECONDS,
            "max_retries": settings.INTERNAL_HTTP_MAX_RETRIES,
            "retry_backoff_seconds": settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
            "circuit_breaker_threshold": settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            "circuit_breaker_cooldown_seconds": (
                settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
            ),
        }

    async def fetch_total_users(self) -> int:
        try:
            payload = await get_internal_json(
                path="/api/v1/internal/stats/users",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("User identity service unavailable") from exc
        try:
            return int(payload["total_users"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceUnavailableException(
                "Unexpected response format from user-service",
            ) from exc

    async def fetch_dashboard_summary(
        self,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        params: dict = {}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        try:
            return await get_internal_json(
                path="/api/v1/internal/dashboard/summary",
                query_params=params or None,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("User service unavailable") from exc

    async def fetch_user_growth(self, start: str, end: str) -> list[dict]:
        try:
            return await get_internal_json(
                path="/api/v1/internal/dashboard/user-growth",
                query_params={"start": start, "end": end},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("User service unavailable") from exc

    async def fetch_usage_trends(self, start: str, end: str) -> dict:
        try:
            return await get_internal_json(
                path="/api/v1/internal/dashboard/usage-trends",
                query_params={"start": start, "end": end},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("User service unavailable") from exc


USER_MGMT_TIMEOUT_SECONDS = 5.0


class UserManagementGateway(BaseGateway):
    """HTTP gateway for user management operations via user-service internal API."""

    def __init__(self) -> None:
        super().__init__(service_name="user-service")

    def _common_kwargs(self) -> dict:
        return {
            "base_url": settings.USER_SERVICE_URL,
            "target_service": self.service_name,
            "secret": settings.INTERNAL_SECRET,
            "caller_service": settings.SERVICE_NAME,
            "timeout": USER_MGMT_TIMEOUT_SECONDS,
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
                raise NotFoundException(detail=exc.detail or "User not found") from exc
            if exc.status_code == 422:
                raise ValidationException(detail=exc.detail or "Validation error") from exc
            if exc.status_code == 403:
                raise AdminPermissionDeniedException(
                    detail=exc.detail or "Permission denied",
                ) from exc
            if exc.status_code == 409:
                raise AdminConflictException(
                    detail=exc.detail or "Resource conflict",
                ) from exc
        raise ServiceUnavailableException("User service unavailable") from exc

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: int | None = None,
    ) -> dict:
        try:
            qp: dict = {"page": page, "page_size": page_size}
            if search:
                qp["search"] = search
            if status is not None:
                qp["status"] = status
            return await get_internal_json(
                path="/api/v1/internal/users",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_user_detail(self, uid: str) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/detail",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def update_user_status(self, uid: str, status: int) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/status",
                json_body={"status": status},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def reset_user_password(self, uid: str, new_password: str) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/reset-password",
                json_body={"new_password": new_password},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def topup_user(
        self, uid: str, amount: int, operator_uid: str, remark: str,
    ) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/topup",
                json_body={
                    "amount": amount,
                    "operator_uid": operator_uid,
                    "remark": remark,
                },
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def adjust_user_balance(
        self, uid: str, amount: int, operator_uid: str, remark: str,
    ) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/adjust-balance",
                json_body={
                    "amount": amount,
                    "operator_uid": operator_uid,
                    "remark": remark,
                },
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_user_transactions(
        self, uid: str, *, page: int = 1, page_size: int = 20,
    ) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/transactions",
                query_params={"page": page, "page_size": page_size},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_user_api_keys(self, uid: str) -> list[dict]:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/api-keys",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def disable_user_api_key(self, uid: str, key_id: int) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/api-keys/{key_id}/disable",
                json_body={},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def enable_user_api_key(self, uid: str, key_id: int) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/api-keys/{key_id}/enable",
                json_body={},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_usage_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
        model_name: str | None = None,
        start: str | None = None,
        end: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        try:
            qp: dict = {"page": page, "page_size": page_size}
            if user_id is not None:
                qp["user_id"] = user_id
            if model_name:
                qp["model_name"] = model_name
            if start:
                qp["start"] = start
            if end:
                qp["end"] = end
            if request_id:
                qp["request_id"] = request_id
            return await get_internal_json(
                path="/api/v1/internal/usage/logs",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_usage_stats(
        self,
        *,
        user_id: int | None = None,
        model_name: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        try:
            qp: dict = {}
            if user_id is not None:
                qp["user_id"] = user_id
            if model_name:
                qp["model_name"] = model_name
            if start:
                qp["start"] = start
            if end:
                qp["end"] = end
            return await get_internal_json(
                path="/api/v1/internal/usage/stats",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_user_usage_stats(
        self,
        uid: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        try:
            qp: dict = {}
            if start:
                qp["start"] = start
            if end:
                qp["end"] = end
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/usage/stats",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_user_usage_analytics(
        self,
        uid: str,
        *,
        range_name: str = "24h",
    ) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/usage/analytics",
                query_params={"range": range_name},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def generate_voucher_codes(
        self,
        *,
        amount: int,
        count: int,
        starts_at,
        expires_at,
        operator_uid: str,
        remark: str | None,
    ) -> dict:
        try:
            return await post_internal_json(
                path="/api/v1/internal/vouchers",
                json_body={
                    "amount": amount,
                    "count": count,
                    "starts_at": format_iso(starts_at),
                    "expires_at": format_iso(expires_at),
                    "operator_uid": operator_uid,
                    "remark": remark,
                },
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_voucher_codes(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: int | None = None,
    ) -> dict:
        try:
            qp: dict = {"page": page, "page_size": page_size}
            if status is not None:
                qp["status"] = status
            return await get_internal_json(
                path="/api/v1/internal/vouchers",
                query_params=qp,
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_voucher_code(self, code_id: int) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/vouchers/{code_id}",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def disable_voucher_code(self, code_id: int, *, operator_uid: str) -> dict:
        try:
            return await request_internal_json(
                method="DELETE",
                path=f"/api/v1/internal/vouchers/{code_id}",
                json_body={"operator_uid": operator_uid},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)
