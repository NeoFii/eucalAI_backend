"""Run service-local Alembic migrations."""

from __future__ import annotations

import argparse
import os

from common.db.schema_version import (
    SERVICE_CONFIGS,
    ServiceMigrationConfig,
    build_service_alembic_config,
)
from scripts.check_service_environment import load_project_dotenv


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
    return build_service_alembic_config(service.service, url=url)


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
