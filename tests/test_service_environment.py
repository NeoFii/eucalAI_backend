from pathlib import Path

from scripts.check_service_environment import (
    format_validation_result,
    validate_environment,
)

_FAKE_MASTER_KEY = "a" * 64


def test_validate_environment_requires_common_secrets_and_service_database_urls():
    result = validate_environment(
        ["admin-service", "user-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
            "ADMIN_DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/admin_db",
            "PROVIDER_SECRET_MASTER_KEY": _FAKE_MASTER_KEY,
        },
    )

    assert not result.ok
    assert "Missing required database URL: USER_DATABASE_URL for user-service" in result.errors


def test_validate_environment_rejects_duplicate_database_urls():
    shared = "mysql+aiomysql://root:pw@localhost:3306/shared_db"
    result = validate_environment(
        ["admin-service", "user-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
            "ADMIN_DATABASE_URL": shared,
            "USER_DATABASE_URL": shared,
            "PROVIDER_SECRET_MASTER_KEY": _FAKE_MASTER_KEY,
        },
    )

    assert not result.ok
    assert any("share the same database URL" in item for item in result.errors)


def test_validate_environment_warns_about_ignored_generic_database_url():
    result = validate_environment(
        ["backend-app"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
            "ADMIN_DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/admin_db",
            "USER_DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/user_db",
            "DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/ignored",
            "PROVIDER_SECRET_MASTER_KEY": _FAKE_MASTER_KEY,
        },
    )

    assert result.ok
    assert "DATABASE_URL is set but ignored; use service-specific *_DATABASE_URL values" in result.warnings


def test_validate_environment_accepts_db_less_router_and_inference_services():
    result = validate_environment(
        ["router-service", "inference-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
            "INFERENCE_SERVICE_SECRET": "test-inference-secret",
        },
    )

    assert result.ok
    assert result.errors == []


def test_validate_environment_rejects_missing_inference_secret():
    result = validate_environment(
        ["router-service", "inference-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
        },
    )

    assert not result.ok
    assert any("INFERENCE_SERVICE_SECRET" in e for e in result.errors)


def test_validate_environment_allows_insecure_dev_for_inference():
    result = validate_environment(
        ["router-service", "inference-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
            "INFERENCE_ALLOW_INSECURE_DEV": "1",
        },
    )

    assert result.ok
    assert any("INFERENCE_ALLOW_INSECURE_DEV" in w for w in result.warnings)


def test_validate_environment_validates_auth_cookie_settings():
    result = validate_environment(
        ["admin-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
            "ADMIN_DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/admin_db",
            "JWT_REFRESH_TOKEN_EXPIRE_DAYS": "0",
            "COOKIE_SAMESITE": "invalid",
            "PROVIDER_SECRET_MASTER_KEY": _FAKE_MASTER_KEY,
        },
    )

    assert not result.ok
    assert "JWT_REFRESH_TOKEN_EXPIRE_DAYS must be greater than 0" in result.errors
    assert "COOKIE_SAMESITE must be one of: lax, strict, none" in result.errors


def test_validate_environment_warns_when_router_master_keys_use_fallback():
    result = validate_environment(
        ["router-service"],
        environ={
            "JWT_SECRET_KEY": "x" * 32,
            "INTERNAL_SECRET": "test_internal_secret_32chars_long!",
        },
    )

    assert result.ok
    assert any("ROUTER_SECRET_MASTER_KEY is empty" in item for item in result.warnings)
    assert any("PROVIDER_SECRET_MASTER_KEY is empty" in item for item in result.warnings)


def test_format_validation_result_renders_errors_and_warnings():
    result = format_validation_result(
        validate_environment(
            ["admin-service"],
            environ={
                "JWT_SECRET_KEY": "short",
                "INTERNAL_SECRET": "",
                "ADMIN_DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/admin_db",
                "DATABASE_URL": "mysql+aiomysql://root:pw@localhost:3306/ignored",
                "PROVIDER_SECRET_MASTER_KEY": _FAKE_MASTER_KEY,
            },
        )
    )

    assert "Environment validation failed:" in result
    assert "JWT_SECRET_KEY must be at least 32 characters" in result
    assert "DATABASE_URL is set but ignored" in result


def test_check_env_script_validates_unknown_services_manually():
    source = (
        Path(__file__).resolve().parent.parent / "scripts" / "check_service_environment.py"
    ).read_text(encoding="utf-8")

    assert "unknown services:" in source
    assert "choices=" not in source
