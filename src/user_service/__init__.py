"""User-service public exports."""

from __future__ import annotations

__all__ = [
    "require_active_user",
]


def __getattr__(name: str):
    if name == "require_active_user":
        from user_service import policies

        return getattr(policies, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
