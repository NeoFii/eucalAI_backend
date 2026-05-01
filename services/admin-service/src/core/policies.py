"""Authorization guards for admin-service."""

from __future__ import annotations

from fastapi import Depends

from core.dependencies import get_current_admin
from core.exceptions import AdminPermissionDeniedException
from models import AdminUser
from common.core.exceptions import AuthenticationException


async def require_active_admin(current_admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """Require an enabled admin account."""

    if current_admin.status == 0:
        raise AuthenticationException(detail="账户已被禁用")
    return current_admin


async def require_super_admin(
    current_admin: AdminUser = Depends(require_active_admin),
) -> AdminUser:
    """Require super-admin privileges."""

    if current_admin.role != "super_admin":
        raise AdminPermissionDeniedException("Super admin required")
    return current_admin
