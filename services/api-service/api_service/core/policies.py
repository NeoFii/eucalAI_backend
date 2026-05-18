"""Authorization guards for api-service user domain."""

from __future__ import annotations

from fastapi import Depends

from api_service.common.core.exceptions import EmailNotVerifiedException, UserDisabledException
from api_service.core.dependencies.user import get_current_user
from api_service.models import User


async def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Require a non-disabled, non-pending user."""

    if current_user.status == 0:
        raise UserDisabledException()
    if current_user.status == 2:
        raise EmailNotVerifiedException()
    return current_user
