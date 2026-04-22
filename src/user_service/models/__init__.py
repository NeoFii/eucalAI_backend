"""User service ORM models."""

from user_service.models.user import User
from user_service.models.user_session import UserSession
from user_service.models.email_verification_code import EmailVerificationCode
from user_service.models.user_api_key import UserApiKey
from user_service.models.balance_transaction import BalanceTransaction
from user_service.models.topup_order import TopupOrder
from user_service.models.api_call_log import ApiCallLog
from user_service.models.usage_stat import UsageStat
from user_service.models.invitation_release_outbox import InvitationReleaseOutbox
from user_service.models.voucher_redemption_code import VoucherRedemptionCode

SERVICE_MODELS = [
    User,
    UserSession,
    EmailVerificationCode,
    UserApiKey,
    BalanceTransaction,
    TopupOrder,
    ApiCallLog,
    UsageStat,
    InvitationReleaseOutbox,
    VoucherRedemptionCode,
]

__all__ = [
    "User",
    "UserSession",
    "EmailVerificationCode",
    "UserApiKey",
    "BalanceTransaction",
    "TopupOrder",
    "ApiCallLog",
    "UsageStat",
    "InvitationReleaseOutbox",
    "VoucherRedemptionCode",
]
