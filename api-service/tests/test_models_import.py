"""Test that all ORM models import correctly without circular dependencies."""

import pytest


# All 20 model classes with their expected __tablename__
MODEL_TABLE_MAP = [
    ("User", "users"),
    ("UserSession", "user_sessions"),
    ("EmailVerificationCode", "email_verification_codes"),
    ("UserApiKey", "user_api_keys"),
    ("BalanceTransaction", "balance_transactions"),
    ("TopupOrder", "topup_orders"),
    ("ApiCallLog", "api_call_logs"),
    ("UsageStat", "usage_stats"),
    ("VoucherRedemptionCode", "voucher_redemption_codes"),
    ("AdminUser", "admin_users"),
    ("AdminAuditLog", "admin_audit_logs"),
    ("AuditActionDefinition", "audit_action_definitions"),
    ("ModelVendor", "model_vendors"),
    ("ModelCategory", "model_categories"),
    ("ModelCatalog", "model_catalog"),
    ("ModelCatalogCategoryMap", "model_catalog_category_map"),
    ("Pool", "pools"),
    ("PoolModelConfig", "pool_model_configs"),
    ("PoolAccount", "pool_accounts"),
    ("RoutingSetting", "routing_settings"),
]

# All 20 expected table names from ORM models in Base.metadata
EXPECTED_TABLES = {
    "users",
    "user_sessions",
    "email_verification_codes",
    "user_api_keys",
    "balance_transactions",
    "topup_orders",
    "api_call_logs",
    "usage_stats",
    "voucher_redemption_codes",
    "admin_users",
    "admin_audit_logs",
    "audit_action_definitions",
    "model_vendors",
    "model_categories",
    "model_catalog",
    "model_catalog_category_map",
    "pools",
    "pool_model_configs",
    "pool_accounts",
    "routing_settings",
}

OLD_CLASS_NAMES = ["SupportedModel", "SupportedModelCategoryMap", "PoolModel"]


def test_no_circular_import():
    """Importing app.model should not raise any errors."""
    import app.model  # noqa: F401


@pytest.mark.parametrize("class_name,tablename", MODEL_TABLE_MAP)
def test_model_tablename(class_name: str, tablename: str):
    """Each model class has the correct __tablename__."""
    import app.model as models

    cls = getattr(models, class_name)
    assert cls.__tablename__ == tablename, (
        f"{class_name}.__tablename__ = {cls.__tablename__!r}, expected {tablename!r}"
    )


def test_all_models_importable():
    """All 20 model classes can be imported from app.model."""
    from app.model import (
        AdminAuditLog,
        AdminUser,
        ApiCallLog,
        AuditActionDefinition,
        BalanceTransaction,
        EmailVerificationCode,
        ModelCatalog,
        ModelCatalogCategoryMap,
        ModelCategory,
        ModelVendor,
        Pool,
        PoolAccount,
        PoolModelConfig,
        RoutingSetting,
        TopupOrder,
        UsageStat,
        User,
        UserApiKey,
        UserSession,
        VoucherRedemptionCode,
    )

    # Verify they are actual classes
    assert User.__tablename__ == "users"
    assert AdminUser.__tablename__ == "admin_users"
    assert ModelCatalog.__tablename__ == "model_catalog"
    assert PoolModelConfig.__tablename__ == "pool_model_configs"
    assert ModelCatalogCategoryMap.__tablename__ == "model_catalog_category_map"
    assert RoutingSetting.__tablename__ == "routing_settings"
    assert AdminAuditLog.__tablename__ == "admin_audit_logs"
    assert AuditActionDefinition.__tablename__ == "audit_action_definitions"
    assert BalanceTransaction.__tablename__ == "balance_transactions"
    assert EmailVerificationCode.__tablename__ == "email_verification_codes"
    assert ModelCategory.__tablename__ == "model_categories"
    assert ModelVendor.__tablename__ == "model_vendors"
    assert Pool.__tablename__ == "pools"
    assert PoolAccount.__tablename__ == "pool_accounts"
    assert TopupOrder.__tablename__ == "topup_orders"
    assert UsageStat.__tablename__ == "usage_stats"
    assert UserApiKey.__tablename__ == "user_api_keys"
    assert UserSession.__tablename__ == "user_sessions"
    assert VoucherRedemptionCode.__tablename__ == "voucher_redemption_codes"
    assert ApiCallLog.__tablename__ == "api_call_logs"


def test_enums_importable():
    """All 3 enum classes can be imported from app.model."""
    from app.model import AdminRole, AdminStatus, PoolAccountStatus

    assert AdminRole.SUPER_ADMIN == 1
    assert AdminStatus.ACTIVE == 1
    assert PoolAccountStatus.ERROR == 3


def test_metadata_contains_all_tables():
    """Base.metadata.tables contains all 20 ORM model table names."""
    import app.model  # noqa: F401 — trigger registration
    from app.common.infra.db.base import Base

    actual_tables = set(Base.metadata.tables.keys())
    missing = EXPECTED_TABLES - actual_tables
    assert not missing, f"Missing tables in metadata: {missing}"


@pytest.mark.parametrize("old_name", OLD_CLASS_NAMES)
def test_old_class_names_not_exported(old_name: str):
    """Renamed classes should not appear in __all__."""
    import app.model as models

    assert old_name not in models.__all__, f"{old_name} should not be in __all__"
    assert not hasattr(models, old_name), f"{old_name} should not be an attribute of models"


def test_all_list_count():
    """__all__ contains exactly 23 names (20 models + 3 enums)."""
    import app.model as models

    assert len(models.__all__) == 23, f"Expected 23, got {len(models.__all__)}"
