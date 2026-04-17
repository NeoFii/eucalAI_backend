"""Shared readiness helpers."""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def check_database_ready(get_engine: Callable[[], AsyncEngine]) -> tuple[bool, str | None]:
    """Run a lightweight database readiness probe."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)


async def build_readiness_response(
    *,
    service_name: str,
    database_check: Callable[[], Awaitable[tuple[bool, str | None]]],
) -> JSONResponse:
    """Build a canonical readiness response."""
    database_ok, database_detail = await database_check()
    ready = database_ok
    payload = {
        "status": "ready" if ready else "not_ready",
        "service": service_name,
        "checks": {
            "database": {
                "status": "ok" if database_ok else "error",
                "detail": database_detail,
            }
        },
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)
