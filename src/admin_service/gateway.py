"""Gateways for admin-service external contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod

from admin_service.config import settings
from common.core.exceptions import (
    ServiceUnavailableException,
    UserNotFoundException,
    ValidationException,
)
from common.gateway.base import BaseGateway
from common.internal import (
    InternalServiceError,
    InternalServiceResponseError,
    get_internal_json,
    post_internal_json,
)

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

    async def fetch_total_users(self) -> int:
        try:
            payload = await get_internal_json(
                base_url=settings.USER_SERVICE_URL,
                target_service=self.service_name,
                path="/api/v1/internal/stats/users",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=IDENTITY_TIMEOUT_SECONDS,
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("User identity service unavailable") from exc
        return int(payload["total_users"])


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

    def _handle_error(self, exc: InternalServiceError) -> None:
        if isinstance(exc, InternalServiceResponseError):
            if exc.status_code == 404:
                raise UserNotFoundException(detail=exc.detail or "User not found") from exc
            if exc.status_code == 422:
                raise ValidationException(detail=exc.detail or "Validation error") from exc
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

    async def get_user_detail(self, uid: int) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/detail",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def update_user_status(self, uid: int, status: int) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/status",
                json_body={"status": status},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def reset_user_password(self, uid: int, new_password: str) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/reset-password",
                json_body={"new_password": new_password},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def topup_user(
        self, uid: int, amount: int, operator_uid: int, remark: str,
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
        self, uid: int, amount: int, operator_uid: int, remark: str,
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
        self, uid: int, *, page: int = 1, page_size: int = 20,
    ) -> dict:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/transactions",
                query_params={"page": page, "page_size": page_size},
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_user_api_keys(self, uid: int) -> list[dict]:
        try:
            return await get_internal_json(
                path=f"/api/v1/internal/users/{uid}/api-keys",
                **self._common_kwargs(),
            )
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def disable_user_api_key(self, uid: int, key_id: int) -> dict:
        try:
            return await post_internal_json(
                path=f"/api/v1/internal/users/{uid}/api-keys/{key_id}/disable",
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
