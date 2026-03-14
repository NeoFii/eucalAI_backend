"""Admin-specific exceptions."""

from fastapi import status

from common.core.exceptions import APIException


class AdminPermissionDeniedException(APIException):
    """Raised when an admin lacks permission for an action."""

    def __init__(self, detail: str = "No permission to perform this action"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            code="permission_denied",
        )


class AdminConflictException(APIException):
    """Raised when an admin action conflicts with existing data."""

    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            code="conflict",
        )
