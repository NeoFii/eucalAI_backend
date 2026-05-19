"""Authorization guards for api-service (user + admin domains).

Plan 05-01 / Task 1b adds the admin-domain guards `require_active_admin` and
`require_super_admin` alongside the existing `require_active_user` (Phase 4).
Both new dependencies wrap `get_current_admin` (Phase 3 D-06, which also
performs token-blacklist checks per D-07).
"""

from __future__ import annotations

from fastapi import Depends

from api_service.common.core.exceptions import (
    AdminPermissionDeniedException,
    EmailNotVerifiedException,
    UserDisabledException,
)
from api_service.core.dependencies.admin import get_current_admin
from api_service.core.dependencies.user import get_current_user
from api_service.models import AdminUser, User
from api_service.models.enums import AdminRole, AdminStatus


async def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Require a non-disabled, non-pending user."""

    if current_user.status == 0:
        raise UserDisabledException()
    if current_user.status == 2:
        raise EmailNotVerifiedException()
    return current_user


async def require_active_admin(
    admin: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    """Require an admin whose status is ACTIVE (not disabled).

    The underlying `get_current_admin` dependency already validates the JWT
    and consults the token blacklist (Phase 3 D-07). This guard adds the
    status check.
    """
    if admin.status != AdminStatus.ACTIVE:
        raise AdminPermissionDeniedException("Admin account inactive")
    return admin


async def require_super_admin(
    admin: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    """Require an admin whose role is SUPER_ADMIN.

    Used by privileged write endpoints (pool / model_catalog / routing
    settings / admin-on-admin CRUD).
    """
    if admin.role != AdminRole.SUPER_ADMIN:
        raise AdminPermissionDeniedException("Super admin permission required")
    return admin


__all__ = [
    "require_active_admin",
    "require_active_user",
    "require_super_admin",
]
