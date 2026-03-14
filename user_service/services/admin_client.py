"""Internal admin-service client used by the user domain."""

from __future__ import annotations

import httpx

from common.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
    ServiceUnavailableException,
)
from common.internal import InternalServiceResponseError, post_internal_json
from user_service.config import settings

ADMIN_TIMEOUT_SECONDS = 3.0


class AdminInvitationClientService:
    """Client for the invitation-code internal contract exposed by admin_service."""

    @staticmethod
    async def consume_invitation_code(code: str, used_by_uid: int) -> None:
        """Consume an invitation code via the admin internal API."""
        try:
            await post_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service="admin-service",
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
            raise AdminInvitationClientService._map_invitation_response_error(exc) from exc
        except httpx.HTTPStatusError as exc:
            raise AdminInvitationClientService._map_invitation_http_error(exc) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableException("Admin invitation service unavailable") from exc

    @staticmethod
    async def release_invitation_code(code: str, used_by_uid: int) -> bool:
        """Release a previously consumed invitation code after a local failure."""
        try:
            payload = await post_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service="admin-service",
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
    def _map_invitation_http_error(exc: httpx.HTTPStatusError):
        response = exc.response
        detail = "Invitation service request failed"
        try:
            payload = response.json()
            detail = payload.get("message") or payload.get("detail") or detail
        except ValueError:
            pass
        return AdminInvitationClientService._map_invitation_status(
            status_code=response.status_code,
            detail=detail,
        )

    @staticmethod
    def _map_invitation_response_error(exc: InternalServiceResponseError):
        return AdminInvitationClientService._map_invitation_status(
            status_code=exc.status_code or 503,
            detail=exc.detail or "Invitation service request failed",
        )

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
