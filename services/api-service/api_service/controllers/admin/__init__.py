"""Admin sub-router aggregator — mounted at /api/v1/admin by core/router.py.

The sub-router itself owns `prefix="/admin"`; `core/router.py` only does
`api_router.include_router(admin_router)` (NO `prefix=` kwarg — that would
double-prefix).

Plan 05-01 / Task 2 wires Plan 05-01's `auth` sub-router. Plans 05-02 and
05-03 will Edit-insert their router includes BELOW their respective anchor
lines so Wave 2 inserts are deterministic and there is no concurrent-
modification race (Warning 3 Option A).

The two anchor lines at the bottom MUST appear EXACTLY as written —
Wave 2 plans grep for these strings as the `old_string` of their Edit
calls. Do NOT reword.
"""

from __future__ import annotations

from fastapi import APIRouter

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Plan 05-01:
from api_service.controllers.admin import auth as _admin_auth  # noqa: E402

admin_router.include_router(_admin_auth.router)

# === Plan 05-02 imports (Wave 2) ===
# (05-02 inserts router include + schema re-exports below this line)
from api_service.controllers.admin import pools as _admin_pools  # noqa: E402

admin_router.include_router(_admin_pools.router)

from api_service.controllers.admin import model_catalog as _admin_model_catalog  # noqa: E402
from api_service.controllers.admin import routing_settings as _admin_routing_settings  # noqa: E402
from api_service.controllers.admin import admin_users as _admin_admin_users  # noqa: E402
from api_service.controllers.admin import audit_logs as _admin_audit_logs  # noqa: E402

admin_router.include_router(_admin_model_catalog.router)
admin_router.include_router(_admin_routing_settings.router)
admin_router.include_router(_admin_admin_users.router)
admin_router.include_router(_admin_audit_logs.router)

# === Plan 05-03 imports (Wave 2) ===
# (05-03 inserts router include + schema re-exports below this line)
from api_service.controllers.admin import users as _admin_users  # noqa: E402

admin_router.include_router(_admin_users.router)

from api_service.controllers.admin import dashboard as _admin_dashboard  # noqa: E402
from api_service.controllers.admin import vouchers as _admin_vouchers  # noqa: E402
from api_service.controllers.admin import route_monitor as _admin_route_monitor  # noqa: E402

admin_router.include_router(_admin_dashboard.router)
admin_router.include_router(_admin_vouchers.router)
admin_router.include_router(_admin_route_monitor.router)

from api_service.controllers.admin import service_logs as _admin_service_logs  # noqa: E402

admin_router.include_router(_admin_service_logs.router)


__all__ = ["admin_router"]
