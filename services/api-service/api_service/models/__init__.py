"""ORM models package — all 19 model classes + 3 enums exported."""

# Enums
from api_service.models.enums import AdminRole, AdminStatus, PoolAccountStatus

# User domain
from api_service.models.user import User
from api_service.models.user_session import UserSession
from api_service.models.email_verification_code import EmailVerificationCode
from api_service.models.user_api_key import UserApiKey
from api_service.models.balance_transaction import BalanceTransaction
from api_service.models.topup_order import TopupOrder
from api_service.models.api_call_log import ApiCallLog
from api_service.models.usage_stat import UsageStat
from api_service.models.voucher_redemption_code import VoucherRedemptionCode

# Admin domain
from api_service.models.admin_user import AdminUser
from api_service.models.admin_audit_log import AdminAuditLog
from api_service.models.audit_action_definition import AuditActionDefinition
from api_service.models.model_catalog import (
    ModelVendor,
    ModelCategory,
    ModelCatalog,
    ModelCatalogCategoryMap,
)
from api_service.models.pool import Pool, PoolModelConfig, PoolAccount
from api_service.models.routing_setting import RoutingSetting

__all__ = [
    # Enums
    "AdminRole",
    "AdminStatus",
    "PoolAccountStatus",
    # User domain
    "User",
    "UserSession",
    "EmailVerificationCode",
    "UserApiKey",
    "BalanceTransaction",
    "TopupOrder",
    "ApiCallLog",
    "UsageStat",
    "VoucherRedemptionCode",
    # Admin domain
    "AdminUser",
    "AdminAuditLog",
    "AuditActionDefinition",
    "ModelVendor",
    "ModelCategory",
    "ModelCatalog",
    "ModelCatalogCategoryMap",
    "Pool",
    "PoolModelConfig",
    "PoolAccount",
    "RoutingSetting",
]
