"""Validate service-specific runtime environment before startup or migrations."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - dependency is installed in normal runtime
    load_dotenv = None


ROOT = Path(__file__).resolve().parent.parent
COMMON_REQUIRED_ENV = ("JWT_SECRET_KEY", "INTERNAL_SECRET")
SERVICE_DATABASE_ENV = {
    "admin-service": "ADMIN_DATABASE_URL",
    "user-service": "USER_DATABASE_URL",
    "router-service": "ROUTER_DATABASE_URL",
    "testing-service": "TESTING_DATABASE_URL",
    "testing-scheduler": "TESTING_DATABASE_URL",
    "testing-worker": "TESTING_DATABASE_URL",
}
# backend-app is a single process that hosts admin/user/testing domains,
# so it needs all three database URLs rather than a single one.
BACKEND_APP_DATABASE_ENVS = (
    "ADMIN_DATABASE_URL",
    "USER_DATABASE_URL",
    "TESTING_DATABASE_URL",
)
AUTH_COOKIE_SERVICES = {"admin-service", "user-service", "backend-app"}
TESTING_RUNTIME_SERVICES = {"testing-service", "testing-worker", "testing-scheduler", "backend-app"}
TESTING_QUEUE_SERVICES = {"testing-worker", "testing-scheduler"}
VALID_COOKIE_SAMESITE = {"lax", "strict", "none"}
PLACEHOLDER_VALUES = {
    "JWT_SECRET_KEY": {"", "your-secret-key", "your-secret-key-change-in-production", "change-me"},
    "INTERNAL_SECRET": {"", "replace-with-a-shared-random-secret"},
}


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_project_dotenv() -> None:
    """Load the repository .env file when available."""
    if load_dotenv is None:
        return
    load_dotenv(ROOT / ".env", override=False)


def _get_env(environ: Mapping[str, str], key: str) -> str:
    return environ.get(key, "").strip()


def _get_first_env(environ: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = _get_env(environ, key)
        if value:
            return value
    return ""


def _parse_bool(value: str, default: bool) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def _validate_positive_integer_env(
    result: ValidationResult,
    environ: Mapping[str, str],
    key: str,
) -> None:
    raw = _get_env(environ, key)
    if not raw:
        return
    try:
        parsed = int(raw)
    except ValueError:
        result.errors.append(f"{key} must be an integer")
        return
    if parsed <= 0:
        result.errors.append(f"{key} must be greater than 0")


def validate_environment(
    selected_services: list[str],
    environ: Mapping[str, str] | None = None,
) -> ValidationResult:
    """Validate required env vars for the selected services."""
    env = environ or os.environ
    result = ValidationResult()

    for key in COMMON_REQUIRED_ENV:
        value = _get_env(env, key)
        if value in PLACEHOLDER_VALUES[key]:
            result.errors.append(f"Missing or placeholder value for {key}")
        elif key == "JWT_SECRET_KEY" and len(value) < 32:
            result.errors.append("JWT_SECRET_KEY must be at least 32 characters")

    database_urls: dict[str, tuple[str, str]] = {}
    for service in selected_services:
        if service == "backend-app":
            for db_env in BACKEND_APP_DATABASE_ENVS:
                value = _get_env(env, db_env)
                if not value:
                    result.errors.append(
                        f"Missing required database URL: {db_env} for backend-app"
                    )
                    continue
                database_urls[f"backend-app:{db_env}"] = (db_env, value)
            continue
        db_env = SERVICE_DATABASE_ENV[service]
        value = _get_env(env, db_env)
        if not value:
            result.errors.append(f"Missing required database URL: {db_env} for {service}")
            continue
        database_urls[service] = (db_env, value)

    reverse_lookup: dict[str, dict[str, list[str]]] = {}
    for service, (db_env, url) in database_urls.items():
        reverse_lookup.setdefault(url, {}).setdefault(db_env, []).append(service)
    for env_map in reverse_lookup.values():
        if len(env_map) > 1:
            joined = ", ".join(
                sorted(
                    service
                    for services in env_map.values()
                    for service in services
                )
            )
            result.errors.append(
                f"Selected services share the same database URL; use distinct schemas or databases: {joined}"
            )

    if _get_env(env, "DATABASE_URL"):
        result.warnings.append("DATABASE_URL is set but ignored; use service-specific *_DATABASE_URL values")

    if set(selected_services) & AUTH_COOKIE_SERVICES:
        _validate_positive_integer_env(result, env, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
        _validate_positive_integer_env(result, env, "JWT_REFRESH_TOKEN_EXPIRE_DAYS")
        cookie_samesite = _get_env(env, "COOKIE_SAMESITE").lower()
        if cookie_samesite and cookie_samesite not in VALID_COOKIE_SAMESITE:
            result.errors.append(
                "COOKIE_SAMESITE must be one of: lax, strict, none"
            )

    if set(selected_services) & TESTING_RUNTIME_SERVICES:
        probe_enabled = _parse_bool(
            _get_first_env(env, "TESTING_PROBE_ENABLED", "PROBE_ENABLED"),
            True,
        )
        redis_url = _get_first_env(
            env,
            "TESTING_BENCHMARK_QUEUE_REDIS_URL",
            "BENCHMARK_QUEUE_REDIS_URL",
        )
        testing_secret = _get_first_env(env, "TESTING_SECRET_MASTER_KEY")

        for service in selected_services:
            if service in TESTING_QUEUE_SERVICES and not redis_url:
                result.errors.append(
                    f"Missing BENCHMARK_QUEUE_REDIS_URL for {service}"
                )
        if probe_enabled and "testing-service" in selected_services and not redis_url:
            result.errors.append(
                "Missing BENCHMARK_QUEUE_REDIS_URL for testing-service while probes are enabled"
            )
        if probe_enabled and not testing_secret:
            result.warnings.append(
                "TESTING_SECRET_MASTER_KEY is empty; encrypted provider probe keys cannot be decrypted"
            )

    if "router-service" in selected_services:
        router_secret = _get_first_env(env, "ROUTER_SECRET_MASTER_KEY")
        provider_secret = _get_first_env(env, "PROVIDER_SECRET_MASTER_KEY")
        if not router_secret:
            result.warnings.append(
                "ROUTER_SECRET_MASTER_KEY is empty; router-service will derive it from JWT_SECRET_KEY"
            )
        if not provider_secret:
            result.warnings.append(
                "PROVIDER_SECRET_MASTER_KEY is empty; router-service will fall back to TESTING_SECRET_MASTER_KEY or JWT-derived key"
            )

    return result


def format_validation_result(result: ValidationResult) -> str:
    """Render a human-readable validation summary."""
    lines: list[str] = []
    if result.errors:
        lines.append("Environment validation failed:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        if lines:
            lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    if not lines:
        lines.append("Environment validation passed")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate service-specific environment variables for the backend",
    )
    parser.add_argument(
        "services",
        nargs="*",
        help="Services to validate; defaults to all runtime services",
    )
    parser.add_argument(
        "--no-dotenv",
        action="store_true",
        help="Skip loading the repository .env file before validation",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.no_dotenv:
        load_project_dotenv()

    unknown = sorted(
        service for service in args.services
        if service not in SERVICE_DATABASE_ENV and service != "backend-app"
    )
    if unknown:
        parser.error(
            "unknown services: " + ", ".join(unknown)
        )

    if args.services:
        selected_services = args.services
    else:
        selected_services = list(SERVICE_DATABASE_ENV.keys())
    result = validate_environment(selected_services)
    print(format_validation_result(result))
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
