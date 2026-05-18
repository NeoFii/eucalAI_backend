"""Auth dependency injection — unified exports for user and admin domains."""

from api_service.core.dependencies.user import get_current_user
from api_service.core.dependencies.admin import (
    get_current_admin,
    get_optional_current_admin,
    get_request_meta,
)

__all__ = [
    "get_current_user",
    "get_current_admin",
    "get_optional_current_admin",
    "get_request_meta",
]
