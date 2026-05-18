"""Test that all repository classes import correctly without circular dependencies."""

import pytest


# All 12 repository classes and their expected inheritance
REPO_CLASSES = [
    ("UserRepository", True),
    ("ApiKeyRepository", True),
    ("BillingRepository", True),
    ("CallLogRepository", False),  # Does not inherit BaseRepository
    ("VoucherRepository", True),
    ("AdminUserRepository", True),
    ("AuditLogRepository", True),
    ("ModelVendorRepository", True),
    ("ModelCategoryRepository", True),
    ("ModelCatalogRepository", True),
    ("PoolRepository", True),
    ("RoutingSettingRepository", False),  # Does not inherit BaseRepository
]


class TestRepositoryImports:
    """Verify all repositories can be imported without circular dependency errors."""

    def test_package_import(self):
        """Importing api_service.repositories should not raise."""
        import api_service.repositories  # noqa: F401

    def test_all_exports_count(self):
        """__all__ should contain exactly 12 names."""
        from api_service.repositories import __all__

        assert len(__all__) == 12

    @pytest.mark.parametrize(
        "class_name,inherits_base",
        REPO_CLASSES,
        ids=[r[0] for r in REPO_CLASSES],
    )
    def test_import_and_inheritance(self, class_name: str, inherits_base: bool):
        """Each repository class should be importable and have correct inheritance."""
        from api_service import repositories
        from api_service.common.infra.db.repository import BaseRepository

        cls = getattr(repositories, class_name)
        if inherits_base:
            assert issubclass(cls, BaseRepository), (
                f"{class_name} should inherit BaseRepository"
            )
        else:
            assert not issubclass(cls, BaseRepository), (
                f"{class_name} should NOT inherit BaseRepository"
            )


class TestUserRepositoryMethods:
    """Verify UserRepository has all expected methods."""

    def test_user_methods(self):
        from api_service.repositories import UserRepository

        user_methods = [
            "get_by_email", "get_by_uid", "count_all", "get_by_id",
            "list_users", "add", "update_rpm_limit", "get_daily_registrations",
            "count_since", "count_in_range",
        ]
        for method in user_methods:
            assert hasattr(UserRepository, method), f"Missing User method: {method}"

    def test_session_methods(self):
        from api_service.repositories import UserRepository

        session_methods = [
            "get_session_by_token_jti", "list_active_sessions_for_user",
            "add_session", "revoke_session",
        ]
        for method in session_methods:
            assert hasattr(UserRepository, method), f"Missing Session method: {method}"

    def test_email_code_methods(self):
        from api_service.repositories import UserRepository

        email_methods = [
            "email_code_count_created_since", "email_code_latest_for_email",
            "email_code_latest_unused_for_email", "email_code_list_unused_for_email",
            "email_code_delete", "email_code_add",
        ]
        for method in email_methods:
            assert hasattr(UserRepository, method), f"Missing EmailCode method: {method}"


class TestBillingRepositoryMethods:
    """Verify BillingRepository has all expected methods."""

    def test_balance_tx_methods(self):
        from api_service.repositories import BillingRepository

        methods = ["add_tx", "exists_by_ref", "list_tx_for_user", "list_tx_all"]
        for method in methods:
            assert hasattr(BillingRepository, method), f"Missing: {method}"

    def test_topup_methods(self):
        from api_service.repositories import BillingRepository

        methods = [
            "topup_add", "topup_get_for_user_by_order_no",
            "topup_list_for_user", "topup_list_all",
        ]
        for method in methods:
            assert hasattr(BillingRepository, method), f"Missing: {method}"

    def test_stat_methods(self):
        from api_service.repositories import BillingRepository

        methods = [
            "stat_get_user_tpm_last_minute", "stat_get_user_stats",
            "stat_get_all_stats", "stat_list_usage_logs",
            "stat_list_analytics_logs", "stat_list_logs_for_hour",
            "stat_get_bucket", "stat_get_daily_platform_stats",
            "stat_get_bucketed_platform_stats", "stat_get_model_call_stats",
            "stat_get_platform_summary", "stat_get_rpm_trend", "stat_get_tpm_trend",
        ]
        for method in methods:
            assert hasattr(BillingRepository, method), f"Missing: {method}"


class TestPoolRepositoryMethods:
    """Verify PoolRepository has all expected methods."""

    def test_pool_methods(self):
        from api_service.repositories import PoolRepository

        methods = [
            "get_by_slug", "list_pools", "get_active_for_routing",
            "get_available_model_slugs", "get_model_cost",
        ]
        for method in methods:
            assert hasattr(PoolRepository, method), f"Missing: {method}"

    def test_model_config_methods(self):
        from api_service.repositories import PoolRepository

        methods = [
            "model_config_get_by_pool_and_model",
            "model_config_remove", "model_config_add",
        ]
        for method in methods:
            assert hasattr(PoolRepository, method), f"Missing: {method}"

    def test_account_methods(self):
        from api_service.repositories import PoolRepository

        methods = ["account_get_by_id_and_pool", "account_add"]
        for method in methods:
            assert hasattr(PoolRepository, method), f"Missing: {method}"
