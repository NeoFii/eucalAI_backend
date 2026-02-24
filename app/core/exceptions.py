"""
自定义异常类
用于服务层统一抛出业务异常
"""

from fastapi import HTTPException, status


class APIException(HTTPException):
    """
    API 基础异常类
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str = "error",
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


class NotFoundException(APIException):
    """
    资源不存在异常
    """

    def __init__(self, detail: str = "请求的资源不存在"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            code="not_found",
        )


class ValidationException(APIException):
    """
    数据验证异常
    """

    def __init__(self, detail: str = "数据验证失败"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            code="validation_error",
        )


class ServiceException(APIException):
    """
    服务内部异常
    """

    def __init__(self, detail: str = "服务暂时不可用"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            code="service_error",
        )


# ==================== 认证相关异常 ====================

class AuthenticationException(APIException):
    """
    认证异常基类
    """

    def __init__(self, detail: str, code: str = "auth_error"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code=code,
        )


class InvalidCredentialsException(AuthenticationException):
    """
    凭证无效异常
    """

    def __init__(self, detail: str = "邮箱或密码错误"):
        super().__init__(detail=detail, code="invalid_credentials")


class UserNotFoundException(AuthenticationException):
    """
    用户不存在异常
    """

    def __init__(self, detail: str = "用户不存在"):
        super().__init__(detail=detail, code="user_not_found")


class UserDisabledException(AuthenticationException):
    """
    用户已被禁用异常
    """

    def __init__(self, detail: str = "账号已被禁用"):
        super().__init__(detail=detail, code="user_disabled")


class EmailNotVerifiedException(AuthenticationException):
    """
    邮箱未验证异常
    """

    def __init__(self, detail: str = "请先验证邮箱"):
        super().__init__(detail=detail, code="email_not_verified")


class TokenException(AuthenticationException):
    """
    令牌异常
    """

    def __init__(self, detail: str, code: str = "token_error"):
        super().__init__(detail=detail, code=code)


class InvalidTokenException(TokenException):
    """
    无效令牌异常
    """

    def __init__(self, detail: str = "无效的令牌"):
        super().__init__(detail=detail, code="invalid_token")


class TokenExpiredException(TokenException):
    """
    令牌过期异常
    """

    def __init__(self, detail: str = "令牌已过期"):
        super().__init__(detail=detail, code="token_expired")


class SessionException(AuthenticationException):
    """
    会话异常
    """

    def __init__(self, detail: str, code: str = "session_error"):
        super().__init__(detail=detail, code=code)


class SessionNotFoundException(SessionException):
    """
    会话不存在异常
    """

    def __init__(self, detail: str = "会话不存在"):
        super().__init__(detail=detail, code="session_not_found")


class SessionRevokedException(SessionException):
    """
    会话已注销异常
    """

    def __init__(self, detail: str = "会话已注销"):
        super().__init__(detail=detail, code="session_revoked")


class SessionExpiredException(SessionException):
    """
    会话已过期异常
    """

    def __init__(self, detail: str = "会话已过期"):
        super().__init__(detail=detail, code="session_expired")


# ==================== 注册相关异常 ====================

class RegistrationException(APIException):
    """
    注册异常基类
    """

    def __init__(self, detail: str, code: str = "registration_error"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code=code,
        )


class EmailAlreadyExistsException(RegistrationException):
    """
    邮箱已被注册异常
    """

    def __init__(self, detail: str = "该邮箱已被注册"):
        super().__init__(detail=detail, code="email_already_exists")


class WeakPasswordException(RegistrationException):
    """
    密码强度不足异常
    """

    def __init__(self, detail: str = "密码强度不足"):
        super().__init__(detail=detail, code="weak_password")


# ==================== 验证码相关异常 ====================

class VerificationException(APIException):
    """
    验证码异常基类
    """

    def __init__(self, detail: str, code: str = "verification_error"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code=code,
        )


class InvalidCodeException(VerificationException):
    """
    验证码错误异常
    """

    def __init__(self, detail: str = "验证码错误"):
        super().__init__(detail=detail, code="invalid_code")


class CodeExpiredException(VerificationException):
    """
    验证码过期异常
    """

    def __init__(self, detail: str = "验证码已过期，请重新获取"):
        super().__init__(detail=detail, code="code_expired")


class CodeNotFoundException(VerificationException):
    """
    验证码不存在异常
    """

    def __init__(self, detail: str = "验证码不存在或已失效"):
        super().__init__(detail=detail, code="code_not_found")


class RateLimitExceededException(APIException):
    """
    频率限制异常
    """

    def __init__(self, detail: str = "操作过于频繁，请稍后再试"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            code="rate_limit_exceeded",
        )
