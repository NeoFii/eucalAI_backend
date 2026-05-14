"""Schema audit fixes: FK relaxation, CHECK constraints, column/table renames.

- admin_audit_logs.actor_admin_id: RESTRICT -> SET NULL + nullable
- audit_action_definitions.category: add CHECK constraint
- pool_accounts.balance: add CHECK(balance >= 0)
- audit_action_definitions: add updated_at, updated_by columns
- pool_models: rename price columns to cost_*
- supported_models: rename price columns to sale_*
- Rename tables: pool_models -> pool_model_configs,
  supported_models -> model_catalog,
  supported_model_category_map -> model_catalog_category_map
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260515_schema_audit_fixes"
down_revision = "20260514_audit_action_defs"
branch_labels = None
depends_on = None


def _fk_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
    ), {"name": constraint_name})
    return bool(result.scalar())


def _check_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'CHECK'"
    ), {"name": constraint_name})
    return bool(result.scalar())


def _col_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col"
    ), {"table": table, "col": column})
    return bool(result.scalar())


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :table"
    ), {"table": table})
    return bool(result.scalar())


def _col_nullable(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT IS_NULLABLE FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col"
    ), {"table": table, "col": column})
    row = result.first()
    return row[0] == "YES" if row else False


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. admin_audit_logs.actor_admin_id: RESTRICT -> SET NULL + nullable ---
    if _fk_exists(conn, "fk_audit_logs_actor"):
        op.drop_constraint("fk_audit_logs_actor", "admin_audit_logs", type_="foreignkey")
    if not _col_nullable(conn, "admin_audit_logs", "actor_admin_id"):
        op.alter_column(
            "admin_audit_logs", "actor_admin_id",
            existing_type=sa.BigInteger(), nullable=True,
        )
    if not _fk_exists(conn, "fk_audit_logs_actor"):
        op.create_foreign_key(
            "fk_audit_logs_actor", "admin_audit_logs", "admin_users",
            ["actor_admin_id"], ["id"], ondelete="SET NULL",
        )

    # --- 2. audit_action_definitions.category: CHECK constraint ---
    if not _check_exists(conn, "chk_audit_category"):
        op.create_check_constraint(
            "chk_audit_category", "audit_action_definitions",
            "category IN ('governance','auth','user_management','model_catalog','routing_config','voucher','pool','unknown')",
        )

    # --- 3. pool_accounts.balance: non-negative CHECK ---
    if not _check_exists(conn, "chk_balance_non_negative"):
        op.create_check_constraint(
            "chk_balance_non_negative", "pool_accounts", "balance >= 0",
        )

    # --- 4. audit_action_definitions: add updated_at, updated_by ---
    if not _col_exists(conn, "audit_action_definitions", "updated_at"):
        op.execute(sa.text(
            "ALTER TABLE `audit_action_definitions` "
            "ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        ))
        op.execute(sa.text(
            "UPDATE `audit_action_definitions` SET `updated_at` = `created_at`"
        ))
    if not _col_exists(conn, "audit_action_definitions", "updated_by"):
        op.add_column(
            "audit_action_definitions",
            sa.Column("updated_by", sa.BigInteger(), nullable=True),
        )
    if not _fk_exists(conn, "fk_audit_action_defs_updated_by"):
        op.create_foreign_key(
            "fk_audit_action_defs_updated_by", "audit_action_definitions", "admin_users",
            ["updated_by"], ["id"], ondelete="SET NULL",
        )

    # --- 5. pool_models: rename price columns to cost_* ---
    if _col_exists(conn, "pool_models", "input_price_per_million"):
        op.execute(sa.text("ALTER TABLE `pool_models` RENAME COLUMN `input_price_per_million` TO `cost_input_per_million`"))
    if _col_exists(conn, "pool_models", "output_price_per_million"):
        op.execute(sa.text("ALTER TABLE `pool_models` RENAME COLUMN `output_price_per_million` TO `cost_output_per_million`"))
    if _col_exists(conn, "pool_models", "cached_input_price_per_million"):
        op.execute(sa.text("ALTER TABLE `pool_models` RENAME COLUMN `cached_input_price_per_million` TO `cost_cached_input_per_million`"))

    # --- 6. supported_models: rename price columns to sale_* ---
    # Must drop CHECK first — MySQL blocks RENAME COLUMN if referenced by CHECK
    if _check_exists(conn, "chk_active_needs_pricing"):
        op.drop_constraint("chk_active_needs_pricing", "supported_models", type_="check")

    if _col_exists(conn, "supported_models", "input_price_per_million"):
        op.execute(sa.text("ALTER TABLE `supported_models` RENAME COLUMN `input_price_per_million` TO `sale_input_per_million`"))
    if _col_exists(conn, "supported_models", "output_price_per_million"):
        op.execute(sa.text("ALTER TABLE `supported_models` RENAME COLUMN `output_price_per_million` TO `sale_output_per_million`"))
    if _col_exists(conn, "supported_models", "cached_input_price_per_million"):
        op.execute(sa.text("ALTER TABLE `supported_models` RENAME COLUMN `cached_input_price_per_million` TO `sale_cached_input_per_million`"))

    # Recreate CHECK constraint with new column names
    if not _check_exists(conn, "chk_active_needs_pricing"):
        op.create_check_constraint(
            "chk_active_needs_pricing", "supported_models",
            "is_active = 0 OR (sale_input_per_million IS NOT NULL AND sale_output_per_million IS NOT NULL)",
        )

    # --- 7. Rename tables ---
    if _table_exists(conn, "pool_models") and not _table_exists(conn, "pool_model_configs"):
        op.execute(sa.text("RENAME TABLE `pool_models` TO `pool_model_configs`"))
    if _table_exists(conn, "supported_model_category_map") and not _table_exists(conn, "model_catalog_category_map"):
        op.execute(sa.text("RENAME TABLE `supported_model_category_map` TO `model_catalog_category_map`"))
    if _table_exists(conn, "supported_models") and not _table_exists(conn, "model_catalog"):
        op.execute(sa.text("RENAME TABLE `supported_models` TO `model_catalog`"))


def downgrade() -> None:
    conn = op.get_bind()

    # --- 7. Revert table renames ---
    if _table_exists(conn, "model_catalog") and not _table_exists(conn, "supported_models"):
        op.execute(sa.text("RENAME TABLE `model_catalog` TO `supported_models`"))
    if _table_exists(conn, "model_catalog_category_map") and not _table_exists(conn, "supported_model_category_map"):
        op.execute(sa.text("RENAME TABLE `model_catalog_category_map` TO `supported_model_category_map`"))
    if _table_exists(conn, "pool_model_configs") and not _table_exists(conn, "pool_models"):
        op.execute(sa.text("RENAME TABLE `pool_model_configs` TO `pool_models`"))

    # --- 6. Revert supported_models column renames ---
    if _col_exists(conn, "supported_models", "sale_input_per_million"):
        op.execute(sa.text("ALTER TABLE `supported_models` RENAME COLUMN `sale_input_per_million` TO `input_price_per_million`"))
    if _col_exists(conn, "supported_models", "sale_output_per_million"):
        op.execute(sa.text("ALTER TABLE `supported_models` RENAME COLUMN `sale_output_per_million` TO `output_price_per_million`"))
    if _col_exists(conn, "supported_models", "sale_cached_input_per_million"):
        op.execute(sa.text("ALTER TABLE `supported_models` RENAME COLUMN `sale_cached_input_per_million` TO `cached_input_price_per_million`"))

    # Revert CHECK constraint
    if _check_exists(conn, "chk_active_needs_pricing"):
        op.drop_constraint("chk_active_needs_pricing", "supported_models", type_="check")
    op.create_check_constraint(
        "chk_active_needs_pricing", "supported_models",
        "is_active = 0 OR (input_price_per_million IS NOT NULL AND output_price_per_million IS NOT NULL)",
    )

    # --- 5. Revert pool_models column renames ---
    if _col_exists(conn, "pool_models", "cost_input_per_million"):
        op.execute(sa.text("ALTER TABLE `pool_models` RENAME COLUMN `cost_input_per_million` TO `input_price_per_million`"))
    if _col_exists(conn, "pool_models", "cost_output_per_million"):
        op.execute(sa.text("ALTER TABLE `pool_models` RENAME COLUMN `cost_output_per_million` TO `output_price_per_million`"))
    if _col_exists(conn, "pool_models", "cost_cached_input_per_million"):
        op.execute(sa.text("ALTER TABLE `pool_models` RENAME COLUMN `cost_cached_input_per_million` TO `cached_input_price_per_million`"))

    # --- 4. Drop audit_action_definitions.updated_at, updated_by ---
    if _fk_exists(conn, "fk_audit_action_defs_updated_by"):
        op.drop_constraint("fk_audit_action_defs_updated_by", "audit_action_definitions", type_="foreignkey")
    if _col_exists(conn, "audit_action_definitions", "updated_by"):
        op.drop_column("audit_action_definitions", "updated_by")
    if _col_exists(conn, "audit_action_definitions", "updated_at"):
        op.drop_column("audit_action_definitions", "updated_at")

    # --- 3. Drop balance CHECK ---
    if _check_exists(conn, "chk_balance_non_negative"):
        op.drop_constraint("chk_balance_non_negative", "pool_accounts", type_="check")

    # --- 2. Drop category CHECK ---
    if _check_exists(conn, "chk_audit_category"):
        op.drop_constraint("chk_audit_category", "audit_action_definitions", type_="check")

    # --- 1. Revert actor_admin_id: SET NULL -> RESTRICT ---
    null_count = conn.execute(sa.text(
        "SELECT COUNT(*) FROM admin_audit_logs WHERE actor_admin_id IS NULL"
    )).scalar()
    if null_count > 0:
        raise RuntimeError(
            f"Cannot downgrade: {null_count} audit log rows have NULL actor_admin_id. "
            "Manually assign a placeholder admin_id before retrying downgrade."
        )
    if _fk_exists(conn, "fk_audit_logs_actor"):
        op.drop_constraint("fk_audit_logs_actor", "admin_audit_logs", type_="foreignkey")
    if _col_nullable(conn, "admin_audit_logs", "actor_admin_id"):
        op.alter_column(
            "admin_audit_logs", "actor_admin_id",
            existing_type=sa.BigInteger(), nullable=False,
        )
    if not _fk_exists(conn, "fk_audit_logs_actor"):
        op.create_foreign_key(
            "fk_audit_logs_actor", "admin_audit_logs", "admin_users",
            ["actor_admin_id"], ["id"], ondelete="RESTRICT",
        )
