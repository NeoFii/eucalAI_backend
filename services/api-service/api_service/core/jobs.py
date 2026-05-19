"""ARQ worker jobs for api-service user domain.

Wave 0 (Task 1 of plan 04-01): 4 cron jobs ported from user-service.
Wave 1 (Task 2 of plan 04-01): adds send_verification_email + _send_smtp_sync helpers.
Plan 05-02 Wave 2 Task 3: adds `run_health_checks` admin cron.

# Phase 5 pre-flight notes (CONTEXT 已解决的开放问题 O-2 + O-4)
# - Source cron cadence verified at services/admin-service/src/core/jobs.py:66:
#       cron(check_channel_health, minute={0, 10, 20, 30, 40, 50})
#   → ported verbatim below as `cron(run_health_checks, minute={...})`.
# - AdminAuditCategory Literal members verified to match source at
#   services/api-service/api_service/schemas/admin/audit_log.py:21 (all 8
#   members preserved: all, governance, auth, user_management,
#   model_catalog, routing_config, voucher, pool).
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select, text

from api_service.common.observability import log_event
from api_service.common.utils.timezone import now
from api_service.core.config import settings
from api_service.core.db import close_db, create_engine, get_db_context, init_session_factory
from api_service.models import EmailVerificationCode

logger = logging.getLogger(__name__)

# Pitfall 9: this string MUST equal the registered function `__name__` (see below).
_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"


def build_redis_settings(redis_url: str | None = None) -> RedisSettings:
    """Build arq RedisSettings from WORKER_QUEUE_REDIS_URL (same shape as arq_pool._build_redis_settings)."""
    parsed = urlparse(redis_url or settings.WORKER_QUEUE_REDIS_URL)
    database = 0
    path = (parsed.path or "").lstrip("/")
    if path:
        database = int(path)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


async def on_worker_startup(ctx: dict) -> None:
    """Initialise DB engine + session factory inside the worker process."""
    create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    )
    init_session_factory()
    ctx["settings"] = settings
    logger.info("api-service worker started")


async def on_worker_shutdown(ctx: dict) -> None:
    """Dispose DB engine on worker shutdown."""
    del ctx
    await close_db()
    logger.info("api-service worker stopped")


async def aggregate_usage_stats(ctx: dict, stat_hour_iso: str | None = None) -> None:
    """Aggregate the previous hour of api_call_logs into usage_stats buckets."""
    del ctx
    from api_service.services.usage_stat_service import UsageStatService  # lazy — usage_stat_service ships in 04-02

    if stat_hour_iso:
        stat_hour = datetime.fromisoformat(stat_hour_iso)
    else:
        stat_hour = now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    async with get_db_context() as db:
        await UsageStatService.aggregate_hour(db, stat_hour)


async def cleanup_expired_verification_codes(ctx: dict) -> None:
    """Remove verification codes past their retention window AND already used."""
    del ctx
    cutoff = now() - timedelta(days=settings.VERIFICATION_CODE_RETENTION_DAYS)
    async with get_db_context() as db:
        records = list(
            (
                await db.execute(
                    select(EmailVerificationCode).where(
                        EmailVerificationCode.expires_at < cutoff,
                        EmailVerificationCode.used_at.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for record in records:
            await db.delete(record)
        await db.commit()


async def cleanup_expired_sessions(ctx: dict) -> None:
    """Remove sessions expired more than 7 days ago."""
    del ctx
    cutoff = now() - timedelta(days=7)
    async with get_db_context() as db:
        await db.execute(
            text("DELETE FROM user_sessions WHERE expires_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await db.commit()
    logger.info("Cleaned up expired sessions older than %s", cutoff)


async def reconcile_balance_ledger(ctx: dict) -> None:
    """Daily reconciliation: detect drift between users.balance and ledger sum."""
    del ctx
    async with get_db_context() as db:
        result = await db.execute(text("""
            SELECT u.id, u.uid, u.balance, COALESCE(SUM(bt.amount), 0) AS tx_sum
            FROM users u
            LEFT JOIN balance_transactions bt ON bt.user_id = u.id
            GROUP BY u.id, u.uid, u.balance
            HAVING u.balance != COALESCE(SUM(bt.amount), 0)
        """))
        drifted = result.all()
        if drifted:
            for row in drifted:
                log_event(
                    logger, logging.ERROR, "balanceDrift",
                    user_id=row.id, uid=row.uid,
                    balance=row.balance, tx_sum=row.tx_sum,
                    delta=row.balance - row.tx_sum,
                )
        else:
            logger.info("Balance reconciliation passed: no drift detected")


def _build_message(email: str, code: str, purpose: str) -> tuple[str, str]:
    """Subject/body builder for the verification email (register/login/verify/reset)."""
    code_expire = settings.EMAIL_CODE_EXPIRE_MINUTES
    if purpose == "register":
        return (
            "[Eucal AI] Registration verification code",
            f"Your verification code is {code}. It expires in {code_expire} minutes.",
        )
    if purpose == "login":
        return (
            "[Eucal AI] Login verification code",
            f"Your login code is {code}. It expires in {code_expire} minutes.",
        )
    if purpose == "verify":
        return (
            "[Eucal AI] Email verification code",
            f"Your email verification code is {code}. It expires in {code_expire} minutes.",
        )
    return (
        "[Eucal AI] Password reset verification code",
        f"Your password reset code is {code}. It expires in {code_expire} minutes.",
    )


def _send_smtp_sync(email: str, code: str, purpose: str) -> None:
    """Blocking SMTP send — wrapped in asyncio.to_thread by the async job below."""
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        # Mock mode (matches source: silent no-op when SMTP not configured).
        logger.debug("emailSendMock email=%s purpose=%s", email, purpose)
        return

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_TLS:
            server.starttls(context=context)
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        subject, body = _build_message(email, code, purpose)
        message = MIMEMultipart("alternative")
        message["From"] = f"{settings.SMTP_FROM} <{settings.SMTP_USER}>"
        message["To"] = email
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))
        server.sendmail(settings.SMTP_USER, email, message.as_string())


async def send_verification_email(ctx: dict, email: str, code: str, purpose: str) -> None:
    """ARQ job — send a verification email synchronously inside a worker thread.

    Retries up to 3 times with linear backoff (5s, 10s, 15s) on SMTP errors.
    After 3 attempts, logs `emailSendFailedPermanently` and swallows the error
    so ARQ does not retry indefinitely (D-02 acceptable tradeoff).
    """
    try:
        await asyncio.to_thread(_send_smtp_sync, email, code, purpose)
    except Exception as exc:  # noqa: BLE001 — broad on purpose, log + Retry
        job_try = ctx.get("job_try", 1)
        if job_try < 3:
            logger.warning("emailSendRetry attempt=%d email=%s error=%s", job_try, email, exc)
            raise Retry(defer=job_try * 5) from exc
        log_event(
            logger,
            logging.ERROR,
            "emailSendFailedPermanently",
            email=email,
            purpose=purpose,
            error=str(exc),
        )


async def run_health_checks(ctx: dict) -> None:
    """ARQ job — proactive channel health probing.

    Ported from `services/admin-service/src/core/jobs.py:check_channel_health`
    in Plan 05-02 / Task 3 (CONTEXT O-2 + O-5). Runs every 10 minutes on the
    existing api-service ARQ worker (no separate worker process — the 2h4g
    constraint forbids a second 350MB resident worker).

    Concurrency is bounded inside `HealthCheckService.run_health_checks`
    by `HEALTH_CHECK_CONCURRENCY=5` (asyncio.Semaphore), so even when many
    pool accounts are configured, in-flight upstream probes never exceed 5.
    """
    del ctx
    # Lazy import — the admin service module loads health_check_service, which
    # in turn imports from `services.admin.pool_service` for the _extract_balance
    # helper. Keeping it lazy avoids forcing the admin service tree to load
    # for non-admin worker invocations.
    from api_service.services.admin.health_check_service import HealthCheckService

    async with get_db_context() as db:
        await HealthCheckService.run_health_checks(db)


def get_worker_settings_kwargs() -> dict:
    """Return the kwargs dict to be applied to WorkerSettings."""
    return {
        "functions": [
            aggregate_usage_stats,
            cleanup_expired_verification_codes,
            cleanup_expired_sessions,
            reconcile_balance_ledger,
            send_verification_email,
            run_health_checks,
        ],
        "cron_jobs": [
            cron(aggregate_usage_stats, minute=0),
            cron(cleanup_expired_verification_codes, hour=3, minute=0),
            cron(cleanup_expired_sessions, hour=3, minute=30),
            cron(reconcile_balance_ledger, hour=4, minute=30),
            # Plan 05-02 / Task 3 — source cadence verbatim (O-2):
            # services/admin-service/src/core/jobs.py:66.
            cron(run_health_checks, minute={0, 10, 20, 30, 40, 50}),
        ],
        "redis_settings": build_redis_settings(),
        "max_jobs": settings.USER_WORKER_CONCURRENCY,
        "job_timeout": settings.USER_JOB_TIMEOUT_SECONDS,
        "on_startup": on_worker_startup,
        "on_shutdown": on_worker_shutdown,
    }
