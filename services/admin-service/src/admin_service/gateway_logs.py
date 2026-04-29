"""Gateway for aggregating logs from all microservices."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from admin_service.config import settings
from common.internal import InternalServiceError, get_internal_json
from common.observability import get_ring_buffer

logger = logging.getLogger(__name__)

_LOG_FETCH_TIMEOUT = 3.0

_REMOTE_SERVICES: list[tuple[str, str]] = [
    ("user-service", "USER_SERVICE_URL"),
    ("router-service", "ROUTER_SERVICE_URL"),
    ("inference-service", "INFERENCE_SERVICE_URL"),
]


class ServiceLogsGateway:
    """Fetch recent logs from all services, with graceful degradation."""

    @staticmethod
    async def fetch_all(
        *,
        services: list[str] | None = None,
        level: str | None = None,
        since: str | None = None,
        until: str | None = None,
        search: str | None = None,
        after_seq: int = 0,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        query_params: dict[str, Any] = {"page": page, "page_size": page_size}
        if level:
            query_params["level"] = level
        if since:
            query_params["since"] = since
        if until:
            query_params["until"] = until
        if search:
            query_params["search"] = search
        if after_seq:
            query_params["after_seq"] = after_seq

        targets = _resolve_targets(services)
        tasks = []
        for svc_name, base_url in targets:
            if svc_name == "admin-service":
                tasks.append(_fetch_local(svc_name, query_params))
            else:
                tasks.append(_fetch_remote(svc_name, base_url, query_params))

        return await asyncio.gather(*tasks)


async def _fetch_local(service: str, params: dict) -> dict[str, Any]:
    buf = get_ring_buffer()
    if buf is None:
        return _result(service, reachable=True, entries=[], total=0, latest_seq=0)
    entries, total, latest_seq = buf.snapshot(
        after_seq=params.get("after_seq", 0),
        level=params.get("level"),
        since=params.get("since"),
        until=params.get("until"),
        search=params.get("search"),
        page=params.get("page", 1),
        page_size=params.get("page_size", 50),
    )
    return _result(service, reachable=True, entries=entries, total=total, latest_seq=latest_seq)


async def _fetch_remote(service: str, base_url: str, params: dict) -> dict[str, Any]:
    try:
        payload = await get_internal_json(
            base_url=base_url,
            target_service=service,
            path="/internal/logs",
            secret=settings.INTERNAL_SECRET,
            caller_service=settings.SERVICE_NAME,
            timeout=_LOG_FETCH_TIMEOUT,
            query_params=params,
            max_retries=0,
            retry_backoff_seconds=0,
            circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            circuit_breaker_cooldown_seconds=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )
        return _result(
            service,
            reachable=True,
            entries=payload.get("entries", []),
            total=payload.get("total", 0),
            latest_seq=payload.get("latest_seq", 0),
        )
    except InternalServiceError as exc:
        logger.warning("Failed to fetch logs from %s: %s", service, exc)
        return _result(service, reachable=False, error=str(exc))
    except Exception as exc:
        logger.warning("Unexpected error fetching logs from %s: %s", service, exc)
        return _result(service, reachable=False, error=str(exc))


def _result(
    service: str,
    *,
    reachable: bool,
    entries: list | None = None,
    total: int = 0,
    latest_seq: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "service": service,
        "reachable": reachable,
        "entries": entries or [],
        "total": total,
        "latest_seq": latest_seq,
        "error": error,
    }


def _resolve_targets(services: list[str] | None) -> list[tuple[str, str]]:
    all_targets: list[tuple[str, str]] = [
        ("admin-service", ""),
    ]
    for svc_name, url_attr in _REMOTE_SERVICES:
        all_targets.append((svc_name, getattr(settings, url_attr)))

    if not services:
        return all_targets
    requested = set(services)
    return [(name, url) for name, url in all_targets if name in requested]
