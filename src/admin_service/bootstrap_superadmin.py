"""CLI for bootstrapping the first super admin_service."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from admin_service.config import settings
from admin_service.models import SERVICE_MODELS
from admin_service.services.bootstrap_service import AdminBootstrapService
from admin_service.db import close_db, create_engine, get_db_context, init_db, init_session_factory
from common.utils.snowflake import configure_snowflake

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap-super-admin",
        description="Bootstrap or verify the first super admin account.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify whether an active super_admin exists; do not create one.",
    )
    parser.add_argument(
        "--skip-init-db",
        action="store_true",
        help="Skip init_db() and assume the schema is already initialized.",
    )
    return parser


async def _setup_runtime(*, skip_init_db: bool) -> None:
    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )
    create_engine(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DATABASE_ECHO,
    )
    init_session_factory()
    if not skip_init_db and settings.AUTO_INIT_DB:
        await init_db(SERVICE_MODELS)


async def _run_check_only() -> int:
    async with get_db_context() as db:
        count = await AdminBootstrapService._count_active_super_admins(db)
    if count > 0:
        logger.info("Found %s active super_admin account(s)", count)
        return 0
    logger.error("No active super_admin account found")
    return 1


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        await _setup_runtime(skip_init_db=args.skip_init_db)
        if args.check_only:
            return await _run_check_only()

        created = await AdminBootstrapService.ensure_super_admin()
        logger.info(
            "super_admin bootstrap finished: created=%s enabled=%s required=%s",
            created,
            settings.BOOTSTRAP_SUPERADMIN_ENABLED,
            settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP,
        )
        return 0
    except Exception:
        logger.exception("super_admin bootstrap command failed")
        return 1
    finally:
        await close_db()


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()


