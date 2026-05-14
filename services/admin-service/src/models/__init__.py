"""Admin service ORM models."""

from models.admin_audit_log import AdminAuditLog
from models.admin_user import AdminUser
from models.audit_action_definition import AuditActionDefinition
from models.model_catalog import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)
from models.pool import Pool, PoolAccount, PoolModel
from models.routing_setting import RoutingSetting

SERVICE_MODELS = [
    AdminAuditLog,
    AdminUser,
    AuditActionDefinition,
    ModelCategory,
    ModelVendor,
    Pool,
    PoolAccount,
    PoolModel,
    RoutingSetting,
    SupportedModel,
    SupportedModelCategoryMap,
]

__all__ = [
    "AdminAuditLog",
    "AdminUser",
    "AuditActionDefinition",
    "ModelCategory",
    "ModelVendor",
    "Pool",
    "PoolAccount",
    "PoolModel",
    "RoutingSetting",
    "SERVICE_MODELS",
    "SupportedModel",
    "SupportedModelCategoryMap",
]
