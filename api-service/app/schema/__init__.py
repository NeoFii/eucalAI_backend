"""Public api-service schema exports.

Phase 4 schemas land incrementally:
- 04-01: auth + common
- 04-02: keys + billing
- 04-03 (final): model_catalog (read-only subset; admin writes in Phase 5)

Plan 05-01 / Task 1a: response envelope primitives are now hoisted to
`app.common.schemas` (D-04). Re-export them here for backward
compatibility with code that does `from app.schema import ApiResponse`.
"""

from app.common.schemas import (
    ApiResponse,
    BaseResponse,
    DateTimeModel,
    ErrorResponse,
)
from app.schema.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    LoginResponseData,
    LoginWithCodeRequest,
    LogoutResponse,
    RefreshResponse,
    RefreshResponseData,
    RefreshTokenResponse,
    RefreshTokenResponseData,
    RegisterRequest,
    RegisterResponse,
    RegisterResponseData,
    ResetPasswordRequest,
    SendEmailCodeRequest,
    UserData,
    UserInfoResponse,
    UserInfoResponseData,
    VerifyEmailRequest,
)
from app.schema.billing import (
    ApiCallLogItem,
    BalanceResponseData,
    BalanceTransactionItem,
    TopupOrderItem,
    UsageAnalyticsBucket,
    UsageAnalyticsBucketCost,
    UsageAnalyticsData,
    UsageAnalyticsModel,
    UsageAnalyticsOverview,
    UsageAnalyticsRange,
    UsageStatItem,
    VoucherRedeemRequest,
    VoucherRedeemResponseData,
    VoucherRedemptionItem,
)
from app.schema.keys import (
    ApiKeyCreateData,
    ApiKeyCreateRequest,
    ApiKeyItem,
    ApiKeyUpdateRequest,
)
from app.schema.model_catalog import (
    ModelCategoryBrief,
    ModelCategoryItem,
    ModelVendorBrief,
    ModelVendorItem,
    SupportedModelDetail,
    SupportedModelItem,
)

__all__ = [
    "ApiCallLogItem",
    "ApiKeyCreateData",
    "ApiKeyCreateRequest",
    "ApiKeyItem",
    "ApiKeyUpdateRequest",
    "ApiResponse",
    "BalanceResponseData",
    "BalanceTransactionItem",
    "BaseResponse",
    "ChangePasswordRequest",
    "ChangePasswordResponse",
    "DateTimeModel",
    "ErrorResponse",
    "LoginRequest",
    "LoginResponse",
    "LoginResponseData",
    "LoginWithCodeRequest",
    "LogoutResponse",
    "ModelCategoryBrief",
    "ModelCategoryItem",
    "ModelVendorBrief",
    "ModelVendorItem",
    "RefreshResponse",
    "RefreshResponseData",
    "RefreshTokenResponse",
    "RefreshTokenResponseData",
    "RegisterRequest",
    "RegisterResponse",
    "RegisterResponseData",
    "ResetPasswordRequest",
    "SendEmailCodeRequest",
    "SupportedModelDetail",
    "SupportedModelItem",
    "TopupOrderItem",
    "UsageAnalyticsBucket",
    "UsageAnalyticsBucketCost",
    "UsageAnalyticsData",
    "UsageAnalyticsModel",
    "UsageAnalyticsOverview",
    "UsageAnalyticsRange",
    "UsageStatItem",
    "UserData",
    "UserInfoResponse",
    "UserInfoResponseData",
    "VerifyEmailRequest",
    "VoucherRedeemRequest",
    "VoucherRedeemResponseData",
    "VoucherRedemptionItem",
]
