"""Unit tests for `PoolService._extract_balance` and related provider parsers.

Plan 05-02 / Task 1 — Pitfall 9: the 4 provider response shapes
(`total_remain`, `points`, `balance`, `remain`) plus the unknown-shape
fallback must all return micro-yuan ints. No DB / FastAPI required.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long",
)
os.environ.setdefault(
    "INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long",
)

import pytest  # noqa: E402

from app.service.admin.pool_service import _extract_balance  # noqa: E402


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # T-5-Pitfall9 — 4 provider response shapes
        ({"data": {"total_remain": 12.34}}, 12_340_000),
        ({"data": {"points": 99}}, 99_000_000),
        ({"data": {"balance": 5.5}}, 5_500_000),
        ({"data": {"remain": 0.01}}, 10_000),
    ],
    ids=["total_remain", "points", "balance", "remain"],
)
def test_extract_balance_provider_shapes(body, expected):
    """All 4 provider response shapes parse into micro-yuan ints."""
    assert _extract_balance(body) == expected


def test_extract_balance_unknown_returns_zero():
    """Unknown shape returns 0 (fail-closed — admin sees stale balance)."""
    assert _extract_balance({"data": {}}) == 0


def test_extract_balance_top_level_balance_key():
    """Top-level `balance` (no `data` wrapper) is also recognised."""
    assert _extract_balance({"balance": 7.5}) == 7_500_000


def test_extract_balance_numeric_data():
    """When `data` itself is a number, treat as the balance (micro-yuan multiplier)."""
    assert _extract_balance({"data": 2.5}) == 2_500_000
