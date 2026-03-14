"""Run service-local Alembic migrations."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from scripts.check_service_environment import load_project_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ServiceMigrationConfig:
    service: str
    package: str
    script_location: Path
    database_env: str


SERVICE_CONFIGS = {
    "admin-service": ServiceMigrationConfig(
        service="admin-service",
        package="admin_service",
        script_location=ROOT / "migrations" / "admin_service",
        database_env="ADMIN_DATABASE_URL",
    ),
    "user-service": ServiceMigrationConfig(
        service="user-service",
        package="user_service",
        script_location=ROOT / "migrations" / "user_service",
        database_env="USER_DATABASE_URL",
    ),
    "router-service": ServiceMigrationConfig(
        service="router-service",
        package="router_service",
        script_location=ROOT / "migrations" / "router_service",
        database_env="ROUTER_DATABASE_URL",
    ),
    "content-service": ServiceMigrationConfig(
        service="content-service",
        package="content_service",
        script_location=ROOT / "migrations" / "content_service",
        database_env="CONTENT_DATABASE_URL",
    ),
    "testing-service": ServiceMigrationConfig(
        service="testing-service",
        package="testing_service",
        script_location=ROOT / "migrations" / "testing_service",
        database_env="TESTING_DATABASE_URL",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run service-local database migrations")
    parser.add_argument(
        "--service",
        required=True,
        choices=sorted(SERVICE_CONFIGS.keys()),
        help="Target service migration namespace",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Override the database URL for this command",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade = subparsers.add_parser("upgrade", help="Upgrade to a revision target")
    upgrade.add_argument("target", nargs="?", default="head")

    downgrade = subparsers.add_parser("downgrade", help="Downgrade to a revision target")
    downgrade.add_argument("target")

    current = subparsers.add_parser("current", help="Show current revision")
    current.add_argument("--verbose", action="store_true")

    history = subparsers.add_parser("history", help="Show revision history")
    history.add_argument("--verbose", action="store_true")

    heads = subparsers.add_parser("heads", help="Show revision heads")
    heads.add_argument("--verbose", action="store_true")

    revision = subparsers.add_parser("revision", help="Create a new revision")
    revision.add_argument("-m", "--message", required=True)
    revision.add_argument("--autogenerate", action="store_true")

    return parser


def resolve_database_url(service: ServiceMigrationConfig, override: str | None) -> str:
    if override:
        return override
    return os.getenv(service.database_env, "").strip()


def load_alembic():
    try:
        from alembic import command
        from alembic.config import Config
    except ModuleNotFoundError as exc:
        if exc.name != "alembic":
            raise
        raise SystemExit(
            "Alembic is not installed in the current environment. "
            "Run `uv sync` before using the migration CLI."
        ) from exc
    return command, Config


def build_alembic_config(service: ServiceMigrationConfig, url: str | None):
    _, Config = load_alembic()
    config = Config()
    config.set_main_option("script_location", str(service.script_location))
    config.set_main_option("prepend_sys_path", str(ROOT))
    config.set_main_option("service_name", service.service)
    config.set_main_option("service_package", service.package)
    if url:
        config.set_main_option("sqlalchemy.url", url)
    return config


def command_requires_database_url(command_name: str, autogenerate: bool = False) -> bool:
    if command_name in {"upgrade", "downgrade", "current"}:
        return True
    if command_name == "revision" and autogenerate:
        return True
    return False


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    load_project_dotenv()

    service = SERVICE_CONFIGS[args.service]
    url = resolve_database_url(service, args.url)
    if command_requires_database_url(args.command, getattr(args, "autogenerate", False)) and not url:
        parser.error(
            f"{args.command} requires a database URL; set {service.database_env} or pass --url"
        )

    config = build_alembic_config(service, url)
    command, _ = load_alembic()

    if args.command == "upgrade":
        command.upgrade(config, args.target)
        return
    if args.command == "downgrade":
        command.downgrade(config, args.target)
        return
    if args.command == "current":
        command.current(config, verbose=args.verbose)
        return
    if args.command == "history":
        command.history(config, verbose=args.verbose)
        return
    if args.command == "heads":
        command.heads(config, verbose=args.verbose)
        return
    if args.command == "revision":
        command.revision(config, message=args.message, autogenerate=args.autogenerate)
        return

    parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
