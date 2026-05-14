"""Integer enum constants for admin-service database fields."""

from __future__ import annotations

from enum import IntEnum


class AdminRole(IntEnum):
    ADMIN = 0
    SUPER_ADMIN = 1


class AdminStatus(IntEnum):
    DISABLED = 0
    ACTIVE = 1


class PoolAccountStatus(IntEnum):
    ACTIVE = 0
    DISABLED = 1
    EXHAUSTED = 2
    ERROR = 3
