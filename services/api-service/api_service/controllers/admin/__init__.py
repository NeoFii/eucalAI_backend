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

# === Plan 05-03 imports (Wave 2) ===
# (05-03 inserts router include + schema re-exports below this line)


__all__ = ["admin_router"]
