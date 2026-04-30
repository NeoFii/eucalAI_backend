"""Monetary precision upgrade: INT fen -> BIGINT micro-yuan (1 yuan = 1,000,000)."""

from __future__ import annotations

from alembic import op

revision = "20260430_02_monetary_precision"
down_revision = "20260429_01_add_api_key_rpm_limit"
branch_labels = None
depends_on = None

_MULTIPLIER = 10_000  # 1 fen = 10,000 micro-yuan

_TABLES = {
    "users": {
        "cols": [
            ("balance", "BIGINT NOT NULL DEFAULT 0"),
            ("frozen_amount", "BIGINT NOT NULL DEFAULT 0"),
            ("used_amount", "BIGINT NOT NULL DEFAULT 0"),
        ],
        "down": [
            ("balance", "INT NOT NULL DEFAULT 0"),
            ("frozen_amount", "INT NOT NULL DEFAULT 0"),
            ("used_amount", "INT NOT NULL DEFAULT 0"),
        ],
    },
    "balance_transactions": {
        "cols": [
            ("amount", "BIGINT NOT NULL"),
            ("balance_before", "BIGINT NOT NULL"),
            ("balance_after", "BIGINT NOT NULL"),
        ],
        "down": [
            ("amount", "INT NOT NULL"),
            ("balance_before", "INT NOT NULL"),
            ("balance_after", "INT NOT NULL"),
        ],
    },
    "api_call_logs": {
        "cols": [
            ("cost", "BIGINT NOT NULL DEFAULT 0"),
            ("provider_cost", "BIGINT NOT NULL DEFAULT 0"),
        ],
        "down": [
            ("cost", "INT NOT NULL DEFAULT 0"),
            ("provider_cost", "INT NOT NULL DEFAULT 0"),
        ],
    },
    "topup_orders": {
        "cols": [("amount", "BIGINT NOT NULL")],
        "down": [("amount", "INT NOT NULL")],
    },
    "usage_stats": {
        "cols": [("total_cost", "BIGINT NOT NULL DEFAULT 0")],
        "down": [("total_cost", "INT NOT NULL DEFAULT 0")],
    },
    "user_api_keys": {
        "cols": [
            ("quota_limit", "BIGINT NOT NULL DEFAULT 0"),
            ("quota_used", "BIGINT NOT NULL DEFAULT 0"),
        ],
        "down": [
            ("quota_limit", "INT NOT NULL DEFAULT 0"),
            ("quota_used", "INT NOT NULL DEFAULT 0"),
        ],
    },
    "voucher_redemption_codes": {
        "cols": [("amount", "BIGINT NOT NULL")],
        "down": [("amount", "INT NOT NULL")],
    },
}


def upgrade() -> None:
    for table, spec in _TABLES.items():
        for col, typedef in spec["cols"]:
            op.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {typedef}")
            op.execute(f"UPDATE `{table}` SET `{col}` = `{col}` * {_MULTIPLIER}")


def downgrade() -> None:
    for table, spec in _TABLES.items():
        for col, typedef in spec["down"]:
            op.execute(f"UPDATE `{table}` SET `{col}` = `{col}` / {_MULTIPLIER}")
            op.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {typedef}")
