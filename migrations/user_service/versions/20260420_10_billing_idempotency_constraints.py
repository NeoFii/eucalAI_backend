"""Add billing idempotency and account-bucket uniqueness constraints."""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "20260420_10_billing_idempotency_constraints"
down_revision = "20260420_09_add_local_foreign_keys"
branch_labels = None
depends_on = None


def _has_index(table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspect(op.get_bind()).get_indexes(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspect(op.get_bind()).get_columns(table_name))


def _has_fk(table_name: str, constraint_name: str) -> bool:
    return any(fk.get("name") == constraint_name for fk in inspect(op.get_bind()).get_foreign_keys(table_name))


def _drop_fk_if_present(table_name: str, constraint_name: str) -> None:
    if _has_fk(table_name, constraint_name):
        op.execute(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint_name}`")


def upgrade() -> None:
    if not _has_index("balance_transactions", "uk_balance_tx_type_ref"):
        op.execute(
            """
            ALTER TABLE `balance_transactions`
                ADD UNIQUE KEY `uk_balance_tx_type_ref` (`type`, `ref_type`, `ref_id`)
            """
        )

    # Local databases that were auto-created from ORM metadata before migration
    # 09 can contain both SQLAlchemy anonymous FKs and the later named FKs. MySQL
    # rebuilds the table when adding a stored generated column and can fail on
    # those duplicate constraints, so normalize them first.
    _drop_fk_if_present("usage_stats", "usage_stats_ibfk_1")
    _drop_fk_if_present("usage_stats", "usage_stats_ibfk_2")

    if not _has_column("usage_stats", "account_api_key_id"):
        op.execute(
            """
            ALTER TABLE `usage_stats`
                ADD COLUMN `account_api_key_id` BIGINT NOT NULL DEFAULT 0
                    COMMENT 'api_key_id with NULL represented as 0 for uniqueness'
            """
        )
        op.execute(
            """
            UPDATE `usage_stats`
               SET `account_api_key_id` = IFNULL(`api_key_id`, 0)
            """
        )

    if not _has_index("usage_stats", "uk_usage_stats_bucket_effective"):
        op.execute(
            """
            ALTER TABLE `usage_stats`
                ADD UNIQUE KEY `uk_usage_stats_bucket_effective`
                    (`user_id`, `account_api_key_id`, `model_name`, `stat_hour`)
            """
        )


def downgrade() -> None:
    if _has_index("usage_stats", "uk_usage_stats_bucket_effective"):
        op.execute("ALTER TABLE `usage_stats` DROP INDEX `uk_usage_stats_bucket_effective`")
    if _has_column("usage_stats", "account_api_key_id"):
        op.execute("ALTER TABLE `usage_stats` DROP COLUMN `account_api_key_id`")
    if _has_index("balance_transactions", "uk_balance_tx_type_ref"):
        op.execute("ALTER TABLE `balance_transactions` DROP INDEX `uk_balance_tx_type_ref`")
