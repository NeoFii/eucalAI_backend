"""Admin-service public exports."""

__all__ = [
    "UserStatsGateway",
    "UserStatsGatewayInterface",
    "require_active_admin",
    "require_super_admin",
]


def __getattr__(name: str):
    if name in {"UserStatsGateway", "UserStatsGatewayInterface"}:
        from admin_service import gateway

        return getattr(gateway, name)
    if name in {"require_active_admin", "require_super_admin"}:
        from admin_service import policies

        return getattr(policies, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
