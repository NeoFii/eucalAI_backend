"""Add balance/usage accounting columns to users.

Introduces the single source of truth for the user balance ledger:
  - balance         (分, user-visible available amount)
  - frozen_amount   (分, in-flight freeze pool for billing pipeline)
  - used_amount     (分, lifetime consumed)
  - total_requests  (lifetime API-call count)
  - total_tokens    (lifetime token count)

All monetary fields are INT storing integer cents (100 = ¥1.00). Float math
is forbidden — see refactor/user-service.md §3.1.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260420_02_users_add_balance_columns"
down_revision = "20260420_01_drop_user_active_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "balance",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="可用余额（分，¥1=100）",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "frozen_amount",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="预冻结中的余额（分）",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "used_amount",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="历史累计消费（分）",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "total_requests",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="历史累计调用次数",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "total_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="历史累计 token 数",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "total_tokens")
    op.drop_column("users", "total_requests")
    op.drop_column("users", "used_amount")
    op.drop_column("users", "frozen_amount")
    op.drop_column("users", "balance")
