"""Admin-service public exports."""

from admin_service.gateway import UserStatsGateway, UserStatsGatewayInterface
from admin_service.policies import require_active_admin, require_super_admin

__all__ = [
    "UserStatsGateway",
    "UserStatsGatewayInterface",
    "require_active_admin",
    "require_super_admin",
]
