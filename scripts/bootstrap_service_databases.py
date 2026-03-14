"""Upgrade service-local databases to the requested migration target."""

from __future__ import annotations

import argparse

from scripts.check_service_environment import load_project_dotenv
from scripts.migrate import (
    SERVICE_CONFIGS,
    build_alembic_config,
    load_alembic,
    resolve_database_url,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upgrade one or more service databases using service-local migrations"
    )
    parser.add_argument(
        "services",
        nargs="*",
        help="Target services; defaults to all service databases",
    )
    parser.add_argument(
        "--target",
        default="head",
        help="Alembic revision target to upgrade to",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and print the execution order without running migrations",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    load_project_dotenv()

    unknown = sorted(service for service in args.services if service not in SERVICE_CONFIGS)
    if unknown:
        parser.error("unknown services: " + ", ".join(unknown))

    selected = args.services or list(SERVICE_CONFIGS.keys())
    missing = []
    resolved = []
    for service_name in selected:
        service = SERVICE_CONFIGS[service_name]
        url = resolve_database_url(service, None)
        if not url:
            missing.append(service.database_env)
            continue
        resolved.append((service, url))

    if missing:
        parser.error(
            "missing service database URLs: " + ", ".join(sorted(set(missing)))
        )

    command, _ = load_alembic()

    for service, url in resolved:
        print(f"[bootstrap] {service.service} -> {args.target}")
        if args.dry_run:
            continue
        config = build_alembic_config(service, url)
        command.upgrade(config, args.target)


if __name__ == "__main__":
    main()
