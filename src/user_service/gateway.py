"""Gateways for user-service external contracts."""

from __future__ import annotations

import httpx
from abc import ABC, abstractmethod

from common.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
    ServiceUnavailableException,
)
from common.gateway.base import BaseGateway
from common.internal import InternalServiceResponseError, post_internal_json
from user_service.config import settings

ADMIN_TIMEOUT_SECONDS = 3.0


class AdminInvitationGatewayInterface(ABC):
    """Contract for admin-service invitation code operations."""

    @abstractmethod
    async def consume_invitation_code(self, code: str, used_by_uid: int) -> None:
        """Consume an invitation code for a user uid."""

    @abstractmethod
    async def release_invitation_code(self, code: str, used_by_uid: int) -> bool:
        """Release a previously consumed invitation code."""


class AdminInvitationGateway(BaseGateway, AdminInvitationGatewayInterface):
    """Gateway for admin-service invitation code operations."""

    def __init__(self) -> None:
        super().__init__(service_name="admin-service")

    async def consume_invitation_code(self, code: str, used_by_uid: int) -> None:
        try:
            await post_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service=self.service_name,
                path="/api/v1/internal/invitation-codes/consume",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=ADMIN_TIMEOUT_SECONDS,
                json_body={"code": code, "used_by_uid": used_by_uid},
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceResponseError as exc:
            raise self._map_invitation_status(
                status_code=exc.status_code or 503,
                detail=exc.detail or "Invitation service request failed",
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = "Invitation service request failed"
            try:
                payload = exc.response.json()
                detail = payload.get("message") or payload.get("detail") or detail
            except ValueError:
                pass
            raise self._map_invitation_status(
                status_code=exc.response.status_code,
                detail=detail,
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableException("Admin invitation service unavailable") from exc

    async def release_invitation_code(self, code: str, used_by_uid: int) -> bool:
        try:
            payload = await post_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service=self.service_name,
                path="/api/v1/internal/invitation-codes/release",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=ADMIN_TIMEOUT_SECONDS,
                json_body={"code": code, "used_by_uid": used_by_uid},
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableException("Admin invitation service unavailable") from exc
        return bool(payload["released"])

    @staticmethod
    def _map_invitation_status(*, status_code: int, detail: str):
        if status_code == 404:
            return InvalidInvitationCodeException(detail=detail)
        if status_code == 409:
            return InvitationCodeUsedException(detail=detail)
        if status_code == 403:
            return InvitationCodeDisabledException(detail=detail)
        if status_code == 410:
            return InvitationCodeExpiredException(detail=detail)
        if status_code >= 500:
            return ServiceUnavailableException("Admin invitation service unavailable")
        return ServiceUnavailableException(detail)


__all__ = ["AdminInvitationGateway", "AdminInvitationGatewayInterface"]
