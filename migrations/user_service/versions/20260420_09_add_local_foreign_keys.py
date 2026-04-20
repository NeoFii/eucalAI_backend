"""Add local foreign keys for user-service owned accounting tables.

These tables live in the same schema as ``users`` and ``user_api_keys``, so
they should enforce local referential integrity at the database layer instead of
relying entirely on application code.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "20260420_09_add_local_foreign_keys"
down_revision = "20260420_08_create_invitation_release_outbox"
branch_labels = None
depends_on = None


def _has_fk(table_name: str, constraint_name: str) -> bool:
    return any(
        fk.get("name") == constraint_name
        for fk in inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def _add_fk_if_missing(table_name: str, constraint_name: str, ddl: str) -> None:
    if not _has_fk(table_name, constraint_name):
        op.execute(ddl)


def upgrade() -> None:
    _add_fk_if_missing(
        "balance_transactions",
        "fk_balance_transactions_user_id",
        """
        ALTER TABLE `balance_transactions`
            ADD CONSTRAINT `fk_balance_transactions_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                ON DELETE CASCADE
        """,
    )
    _add_fk_if_missing(
        "topup_orders",
        "fk_topup_orders_user_id",
        """
        ALTER TABLE `topup_orders`
            ADD CONSTRAINT `fk_topup_orders_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                ON DELETE CASCADE
        """,
    )
    _add_fk_if_missing(
        "api_call_logs",
        "fk_api_call_logs_user_id",
        """
        ALTER TABLE `api_call_logs`
            ADD CONSTRAINT `fk_api_call_logs_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                ON DELETE CASCADE
        """,
    )
    _add_fk_if_missing(
        "api_call_logs",
        "fk_api_call_logs_api_key_id",
        """
        ALTER TABLE `api_call_logs`
            ADD CONSTRAINT `fk_api_call_logs_api_key_id`
                FOREIGN KEY (`api_key_id`) REFERENCES `user_api_keys` (`id`)
                ON DELETE SET NULL
        """,
    )
    _add_fk_if_missing(
        "usage_stats",
        "fk_usage_stats_user_id",
        """
        ALTER TABLE `usage_stats`
            ADD CONSTRAINT `fk_usage_stats_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                ON DELETE CASCADE
        """,
    )
    _add_fk_if_missing(
        "usage_stats",
        "fk_usage_stats_api_key_id",
        """
        ALTER TABLE `usage_stats`
            ADD CONSTRAINT `fk_usage_stats_api_key_id`
                FOREIGN KEY (`api_key_id`) REFERENCES `user_api_keys` (`id`)
                ON DELETE SET NULL
        """,
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE `usage_stats`
            DROP FOREIGN KEY `fk_usage_stats_api_key_id`,
            DROP FOREIGN KEY `fk_usage_stats_user_id`
        """
    )
    op.execute(
        """
        ALTER TABLE `api_call_logs`
            DROP FOREIGN KEY `fk_api_call_logs_api_key_id`,
            DROP FOREIGN KEY `fk_api_call_logs_user_id`
        """
    )
    op.execute(
        """
        ALTER TABLE `topup_orders`
            DROP FOREIGN KEY `fk_topup_orders_user_id`
        """
    )
    op.execute(
        """
        ALTER TABLE `balance_transactions`
            DROP FOREIGN KEY `fk_balance_transactions_user_id`
        """
    )
