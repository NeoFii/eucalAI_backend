"""Admin service ORM models."""

from models.admin_audit_log import AdminAuditLog
from models.admin_user import AdminUser
from models.model_catalog import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)
from models.pool import Pool, PoolAccount, PoolModel
from models.routing_config import ProviderCredential, RoutingConfig
from models.routing_setting import RoutingSetting

SERVICE_MODELS = [
    AdminAuditLog,
    AdminUser,
    ModelCategory,
    ModelVendor,
    Pool,
    PoolAccount,
    PoolModel,
    ProviderCredential,
    RoutingConfig,
    RoutingSetting,
    SupportedModel,
    SupportedModelCategoryMap,
]

__all__ = [
    "AdminAuditLog",
    "AdminUser",
    "ModelCategory",
    "ModelVendor",
    "Pool",
    "PoolAccount",
    "PoolModel",
    "ProviderCredential",
    "RoutingConfig",
    "RoutingSetting",
    "SERVICE_MODELS",
    "SupportedModel",
    "SupportedModelCategoryMap",
]
