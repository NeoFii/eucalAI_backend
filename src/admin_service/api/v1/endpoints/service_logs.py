"""Service logs monitoring endpoint — super_admin only."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from admin_service.gateway_logs import ServiceLogsGateway
from admin_service.models import AdminUser
from admin_service.policies import require_super_admin

router = APIRouter(prefix="/service-logs", tags=["admin-service-logs"])


@router.get("", summary="Aggregate recent logs from all services")
async def get_service_logs(
    _admin: AdminUser = Depends(require_super_admin),
    service: str | None = Query(None, max_length=50),
    level: str | None = Query(None, max_length=10),
    since: str | None = Query(None, max_length=30),
    until: str | None = Query(None, max_length=30),
    search: str | None = Query(None, max_length=200),
    after_seq: int = Query(0, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    services = [service] if service else None
    results = await ServiceLogsGateway.fetch_all(
        services=services,
        level=level,
        since=since,
        until=until,
        search=search,
        after_seq=after_seq,
        page=page,
        page_size=page_size,
    )

    merged = []
    total = 0
    for r in results:
        for entry in r.get("entries", []):
            if "service" not in entry:
                entry["service"] = r["service"]
            merged.append(entry)
        total += r.get("total", 0)
    merged.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "results": results,
            "items": merged,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
