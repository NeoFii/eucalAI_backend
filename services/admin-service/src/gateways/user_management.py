"""Admin control-plane facade for user-service.

This module proxies user-management and voucher operations to user-service
via HMAC-signed internal HTTP calls. It is intentionally part of admin_service
(not a separate package) because admin is the only consumer of these facades.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.config import settings
from core.exceptions import AdminConflictException, AdminPermissionDeniedException
from common.core.exceptions import NotFoundException, ValidationException
from common.gateway.base import BaseGateway
from common.utils.timezone import format_iso

IDENTITY_TIMEOUT_SECONDS = 3.0
USER_MGMT_TIMEOUT_SECONDS = 5.0


class UserStatsGatewayInterface(ABC):
    """Contract for user-service statistics needed by admin-service."""

    @abstractmethod
    async def fetch_total_users(self) -> int:
        """Return the total user count."""


class UserStatsGateway(BaseGateway, UserStatsGatewayInterface):
    """HTTP gateway for user-service statistics."""

    def __init__(self) -> None:
        super().__init__(
            "user-service",
            base_url=settings.USER_SERVICE_URL,
            timeout=IDENTITY_TIMEOUT_SECONDS,
        )

    async def fetch_total_users(self) -> int:
        payload = await self._get("/api/v1/internal/stats/users")
        try:
            return int(payload["total_users"])
        except (KeyError, TypeError, ValueError) as exc:
            from common.core.exceptions import ServiceUnavailableException
            raise ServiceUnavailableException(
                "Unexpected response format from user-service",
            ) from exc

    async def fetch_dashboard_summary(
        self, start: str | None = None, end: str | None = None,
    ) -> dict:
        params: dict = {}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return await self._get(
            "/api/v1/internal/dashboard/summary", query_params=params or None,
        )

    async def fetch_user_growth(self, start: str, end: str) -> list[dict]:
        return await self._get(
            "/api/v1/internal/dashboard/user-growth",
            query_params={"start": start, "end": end},
        )

    async def fetch_usage_trends(self, start: str, end: str) -> dict:
        return await self._get(
            "/api/v1/internal/dashboard/usage-trends",
            query_params={"start": start, "end": end},
        )

    async def fetch_rpm_trend(
        self, start: str, end: str, bucket_seconds: int,
    ) -> dict:
        return await self._get(
            "/api/v1/internal/dashboard/rpm-trend",
            query_params={"start": start, "end": end, "bucket_seconds": bucket_seconds},
        )


class UserManagementGateway(BaseGateway):
    """HTTP gateway for user management operations via user-service internal API."""

    def __init__(self) -> None:
        super().__init__(
            "user-service",
            base_url=settings.USER_SERVICE_URL,
            timeout=USER_MGMT_TIMEOUT_SECONDS,
            error_map={
                404: NotFoundException,
                422: ValidationException,
                403: AdminPermissionDeniedException,
                409: AdminConflictException,
            },
        )

    async def list_users(
        self, *, page: int = 1, page_size: int = 20,
        search: str | None = None, status: int | None = None,
    ) -> dict:
        qp: dict = {"page": page, "page_size": page_size}
        if search:
            qp["search"] = search
        if status is not None:
            qp["status"] = status
        return await self._get("/api/v1/internal/users", query_params=qp)

    async def get_user_detail(self, uid: str) -> dict:
        return await self._get(f"/api/v1/internal/users/{uid}/detail")

    async def update_user_status(self, uid: str, status: int) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/status", {"status": status},
        )

    async def reset_user_password(self, uid: str, new_password: str) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/reset-password",
            {"new_password": new_password},
        )

    async def topup_user(
        self, uid: str, amount: int, operator_uid: str, remark: str,
    ) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/topup",
            {"amount": amount, "operator_uid": operator_uid, "remark": remark},
        )

    async def adjust_user_balance(
        self, uid: str, amount: int, operator_uid: str, remark: str,
    ) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/adjust-balance",
            {"amount": amount, "operator_uid": operator_uid, "remark": remark},
        )

    async def update_user_rpm(
        self, uid: str, *, rpm_limit: int | None, operator_uid: str, remark: str,
    ) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/rpm",
            {"rpm_limit": rpm_limit, "operator_uid": operator_uid, "remark": remark},
        )

    async def list_user_transactions(
        self, uid: str, *, page: int = 1, page_size: int = 20,
    ) -> dict:
        return await self._get(
            f"/api/v1/internal/users/{uid}/transactions",
            query_params={"page": page, "page_size": page_size},
        )

    async def list_user_api_keys(self, uid: str) -> list[dict]:
        return await self._get(f"/api/v1/internal/users/{uid}/api-keys")

    async def disable_user_api_key(self, uid: str, key_id: int) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/api-keys/{key_id}/disable", {},
        )

    async def enable_user_api_key(self, uid: str, key_id: int) -> dict:
        return await self._post(
            f"/api/v1/internal/users/{uid}/api-keys/{key_id}/enable", {},
        )

    async def list_usage_logs(
        self, *, page: int = 1, page_size: int = 20,
        user_id: int | None = None, user_uid: str | None = None,
        model_name: str | None = None,
        start: str | None = None, end: str | None = None,
        request_id: str | None = None, api_key_id: int | None = None,
    ) -> dict:
        qp: dict = {"page": page, "page_size": page_size}
        if user_id is not None:
            qp["user_id"] = user_id
        if user_uid:
            qp["user_uid"] = user_uid
        if model_name:
            qp["model_name"] = model_name
        if start:
            qp["start"] = start
        if end:
            qp["end"] = end
        if request_id:
            qp["request_id"] = request_id
        if api_key_id is not None:
            qp["api_key_id"] = api_key_id
        return await self._get("/api/v1/internal/usage/logs", query_params=qp)

    async def list_usage_stats(
        self, *, user_id: int | None = None, user_uid: str | None = None,
        model_name: str | None = None,
        start: str | None = None, end: str | None = None,
        api_key_id: int | None = None,
    ) -> list[dict]:
        qp: dict = {}
        if user_id is not None:
            qp["user_id"] = user_id
        if user_uid:
            qp["user_uid"] = user_uid
        if model_name:
            qp["model_name"] = model_name
        if start:
            qp["start"] = start
        if end:
            qp["end"] = end
        if api_key_id is not None:
            qp["api_key_id"] = api_key_id
        return await self._get("/api/v1/internal/usage/stats", query_params=qp)

    async def get_user_usage_stats(
        self, uid: str, *, start: str | None = None, end: str | None = None,
        model_name: str | None = None, api_key_id: int | None = None,
    ) -> list[dict]:
        qp: dict = {}
        if start:
            qp["start"] = start
        if end:
            qp["end"] = end
        if model_name:
            qp["model_name"] = model_name
        if api_key_id is not None:
            qp["api_key_id"] = api_key_id
        return await self._get(
            f"/api/v1/internal/users/{uid}/usage/stats", query_params=qp,
        )

    async def get_user_usage_analytics(
        self, uid: str, *, range_name: str | None = None,
        start: str | None = None, end: str | None = None,
        api_key_id: int | None = None,
    ) -> dict:
        qp: dict = {}
        if range_name:
            qp["range"] = range_name
        if start:
            qp["start"] = start
        if end:
            qp["end"] = end
        if api_key_id is not None:
            qp["api_key_id"] = api_key_id
        return await self._get(
            f"/api/v1/internal/users/{uid}/usage/analytics", query_params=qp,
        )

    async def generate_voucher_codes(
        self, *, amount: int, count: int, starts_at, expires_at,
        operator_uid: str, remark: str | None,
    ) -> dict:
        return await self._post(
            "/api/v1/internal/vouchers",
            {
                "amount": amount,
                "count": count,
                "starts_at": format_iso(starts_at),
                "expires_at": format_iso(expires_at),
                "operator_uid": operator_uid,
                "remark": remark,
            },
        )

    async def list_voucher_codes(
        self, *, page: int = 1, page_size: int = 20, status: int | None = None,
    ) -> dict:
        qp: dict = {"page": page, "page_size": page_size}
        if status is not None:
            qp["status"] = status
        return await self._get("/api/v1/internal/vouchers", query_params=qp)

    async def get_voucher_code(self, code_id: int) -> dict:
        return await self._get(f"/api/v1/internal/vouchers/{code_id}")

    async def disable_voucher_code(self, code_id: int, *, operator_uid: str) -> dict:
        return await self._request(
            "DELETE",
            f"/api/v1/internal/vouchers/{code_id}",
            json_body={"operator_uid": operator_uid},
        )
