"""Audit helper shared across controllers."""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from services.audit_service import AdminAuditService

logger = logging.getLogger(__name__)


async def safe_audit_commit(db: AsyncSession, **audit_kwargs) -> None:
    """Write an audit record and commit. On failure, log the full audit payload
    at CRITICAL level so it can be recovered from logs."""
    try:
        await AdminAuditService.record(db, **audit_kwargs)
        await db.commit()
    except Exception:
        logger.critical(
            "Audit commit failed after successful gateway operation: %s",
            json.dumps(audit_kwargs, default=str),
        )
        await db.rollback()
