"""User-specific exceptions."""

from fastapi import status

from common.core.exceptions import APIException


class InsufficientBalanceException(APIException):
    def __init__(self, detail: str = "余额不足"):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
            code="insufficient_balance",
        )


class UserConflictException(APIException):
    def __init__(self, detail: str = "资源已存在"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            code="conflict",
        )
