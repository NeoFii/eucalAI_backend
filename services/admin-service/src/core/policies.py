"""Authorization guards for admin-service."""

from __future__ import annotations

from fastapi import Depends

from common.core.exceptions import AuthenticationException
from core.dependencies import get_current_admin
from core.enums import AdminRole, AdminStatus
from core.exceptions import AdminPermissionDeniedException
from models import AdminUser


async def require_active_admin(current_admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """Require an enabled admin account."""

    if current_admin.status == AdminStatus.DISABLED:
        raise AuthenticationException(detail="账户已被禁用")
    return current_admin


async def require_super_admin(
    current_admin: AdminUser = Depends(require_active_admin),
) -> AdminUser:
    """Require super-admin privileges."""

    if current_admin.role != AdminRole.SUPER_ADMIN:
        raise AdminPermissionDeniedException("Super admin required")
    return current_admin
