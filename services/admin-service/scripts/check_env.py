"""Validate admin-service runtime environment before startup."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

SERVICE_ROOT = Path(__file__).resolve().parent.parent

PLACEHOLDER_VALUES = {
    "JWT_SECRET_KEY": {"", "your-secret-key", "your-secret-key-change-in-production", "change-me"},
    "INTERNAL_SECRET": {"", "replace-with-a-shared-random-secret"},
}
VALID_COOKIE_SAMESITE = {"lax", "strict", "none"}


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_dotenv_file() -> None:
    if load_dotenv is None:
        return
    env_file = SERVICE_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def _get_env(environ: Mapping[str, str], key: str) -> str:
    return environ.get(key, "").strip()


def _validate_positive_integer_env(
    result: ValidationResult, environ: Mapping[str, str], key: str
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


def validate_environment(environ: Mapping[str, str] | None = None) -> ValidationResult:
    env = environ or os.environ
    result = ValidationResult()

    jwt_key = _get_env(env, "JWT_SECRET_KEY")
    if jwt_key in PLACEHOLDER_VALUES["JWT_SECRET_KEY"]:
        result.errors.append("Missing or placeholder value for JWT_SECRET_KEY")
    elif len(jwt_key) < 32:
        result.errors.append("JWT_SECRET_KEY must be at least 32 characters")

    internal = _get_env(env, "INTERNAL_SECRET")
    if internal in PLACEHOLDER_VALUES["INTERNAL_SECRET"]:
        result.errors.append("Missing or placeholder value for INTERNAL_SECRET")

    if not _get_env(env, "ADMIN_DATABASE_URL"):
        result.errors.append("Missing required: ADMIN_DATABASE_URL")

    provider_key = _get_env(env, "PROVIDER_SECRET_MASTER_KEY")
    if not provider_key:
        result.errors.append(
            "PROVIDER_SECRET_MASTER_KEY is required "
            "(must be 64-char hex string for AES-256-GCM)"
        )
    elif len(provider_key) != 64:
        result.errors.append(
            "PROVIDER_SECRET_MASTER_KEY must be exactly 64 hex characters (32 bytes)"
        )

    _validate_positive_integer_env(result, env, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    _validate_positive_integer_env(result, env, "JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    cookie_samesite = _get_env(env, "COOKIE_SAMESITE").lower()
    if cookie_samesite and cookie_samesite not in VALID_COOKIE_SAMESITE:
        result.errors.append("COOKIE_SAMESITE must be one of: lax, strict, none")

    if _get_env(env, "DATABASE_URL"):
        result.warnings.append("DATABASE_URL is set but ignored; use ADMIN_DATABASE_URL")

    return result


def format_validation_result(result: ValidationResult) -> str:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate admin-service environment")
    parser.add_argument("--no-dotenv", action="store_true", help="Skip loading .env file")
    args = parser.parse_args()

    if not args.no_dotenv:
        load_dotenv_file()

    result = validate_environment()
    print(format_validation_result(result))
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
