"""Enforce integer enums, CHECK constraints, indexes, and FK fixes.

- admin_users.role: VARCHAR(20) -> SMALLINT with CHECK(role IN (0, 1))
- admin_users.status: add CHECK(status IN (0, 1))
- pool_accounts.status: VARCHAR(16) -> SMALLINT with CHECK(status IN (0, 1, 2, 3))
- pools.created_by / pool_accounts.created_by: RESTRICT -> SET NULL, nullable
- routing_settings.updated_by: add FK -> admin_users.id ON DELETE SET NULL
- admin_audit_logs.created_at: add index for time-range queries
- pool_models: add composite index for routing lookups
- pool_accounts: add composite index for routing lookups
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260514_enum_constraints"
down_revision = "20260514_normalize_price_columns"
branch_labels = None
depends_on = None


def _col_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col"
    ), {"table": table, "col": column})
    return bool(result.scalar())


def _col_type(conn, table: str, column: str) -> str | None:
    result = conn.execute(sa.text(
        "SELECT DATA_TYPE FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col"
    ), {"table": table, "col": column})
    row = result.first()
    return row[0] if row else None


def _col_nullable(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT IS_NULLABLE FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col"
    ), {"table": table, "col": column})
    row = result.first()
    return row[0] == "YES" if row else False


def _fk_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
    ), {"name": constraint_name})
    return bool(result.scalar())


def _fk_delete_rule(conn, constraint_name: str) -> str | None:
    result = conn.execute(sa.text(
        "SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name"
    ), {"name": constraint_name})
    row = result.first()
    return row[0] if row else None


def _check_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'CHECK'"
    ), {"name": constraint_name})
    return bool(result.scalar())


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND INDEX_NAME = :name"
    ), {"name": index_name})
    return bool(result.scalar())


def upgrade() -> None:
    conn = op.get_bind()

    # --- admin_users.role: String -> SmallInteger (idempotent) ---
    if _col_exists(conn, "admin_users", "role_new"):
        conn.execute(sa.text("ALTER TABLE `admin_users` DROP COLUMN `role_new`"))
    role_type = _col_type(conn, "admin_users", "role")
    if role_type == "varchar":
        op.add_column("admin_users", sa.Column("role_new", sa.SmallInteger(), nullable=True))
        op.execute(
            "UPDATE admin_users SET role_new = CASE role "
            "WHEN 'admin' THEN 0 "
            "WHEN 'super_admin' THEN 1 "
            "ELSE 0 END"
        )
        op.alter_column("admin_users", "role_new", existing_type=sa.SmallInteger(), nullable=False)
        op.drop_column("admin_users", "role")
        op.alter_column("admin_users", "role_new", existing_type=sa.SmallInteger(), new_column_name="role")
    elif role_type == "smallint" and _col_nullable(conn, "admin_users", "role"):
        op.alter_column("admin_users", "role", existing_type=sa.SmallInteger(), nullable=False)

    if not _check_exists(conn, "chk_admin_users_role"):
        op.create_check_constraint("chk_admin_users_role", "admin_users", "role IN (0, 1)")

    # --- admin_users.status: add CHECK ---
    if not _check_exists(conn, "chk_admin_users_status"):
        op.create_check_constraint("chk_admin_users_status", "admin_users", "status IN (0, 1)")

    # --- pool_accounts.status: String -> SmallInteger (idempotent) ---
    if _col_exists(conn, "pool_accounts", "status_new"):
        conn.execute(sa.text("ALTER TABLE `pool_accounts` DROP COLUMN `status_new`"))
    status_type = _col_type(conn, "pool_accounts", "status")
    if status_type == "varchar":
        op.add_column("pool_accounts", sa.Column("status_new", sa.SmallInteger(), nullable=True))
        op.execute(
            "UPDATE pool_accounts SET status_new = CASE status "
            "WHEN 'active' THEN 0 "
            "WHEN 'disabled' THEN 1 "
            "WHEN 'exhausted' THEN 2 "
            "WHEN 'error' THEN 3 "
            "ELSE 0 END"
        )
        op.alter_column("pool_accounts", "status_new", existing_type=sa.SmallInteger(), nullable=False)
        op.drop_column("pool_accounts", "status")
        op.alter_column("pool_accounts", "status_new", existing_type=sa.SmallInteger(), new_column_name="status")
    elif status_type == "smallint" and _col_nullable(conn, "pool_accounts", "status"):
        op.alter_column("pool_accounts", "status", existing_type=sa.SmallInteger(), nullable=False)

    if not _check_exists(conn, "chk_pool_accounts_status"):
        op.create_check_constraint(
            "chk_pool_accounts_status", "pool_accounts", "status IN (0, 1, 2, 3)"
        )

    # --- pools.created_by: RESTRICT -> SET NULL ---
    if _fk_exists(conn, "pools_ibfk_1"):
        op.drop_constraint("pools_ibfk_1", "pools", type_="foreignkey")
    if _fk_exists(conn, "fk_pools_created_by") and _fk_delete_rule(conn, "fk_pools_created_by") == "RESTRICT":
        op.drop_constraint("fk_pools_created_by", "pools", type_="foreignkey")
    if not _col_nullable(conn, "pools", "created_by"):
        op.alter_column("pools", "created_by", existing_type=sa.BigInteger(), nullable=True)
    if not _fk_exists(conn, "fk_pools_created_by"):
        op.create_foreign_key(
            "fk_pools_created_by", "pools", "admin_users",
            ["created_by"], ["id"], ondelete="SET NULL",
        )

    # --- pool_accounts.created_by: RESTRICT -> SET NULL ---
    if _fk_exists(conn, "pool_accounts_ibfk_2"):
        op.drop_constraint("pool_accounts_ibfk_2", "pool_accounts", type_="foreignkey")
    if _fk_exists(conn, "fk_pool_accounts_created_by") and _fk_delete_rule(conn, "fk_pool_accounts_created_by") == "RESTRICT":
        op.drop_constraint("fk_pool_accounts_created_by", "pool_accounts", type_="foreignkey")
    if not _col_nullable(conn, "pool_accounts", "created_by"):
        op.alter_column("pool_accounts", "created_by", existing_type=sa.BigInteger(), nullable=True)
    if not _fk_exists(conn, "fk_pool_accounts_created_by"):
        op.create_foreign_key(
            "fk_pool_accounts_created_by", "pool_accounts", "admin_users",
            ["created_by"], ["id"], ondelete="SET NULL",
        )

    # --- routing_settings.updated_by: add FK ---
    if not _fk_exists(conn, "fk_routing_settings_updated_by"):
        op.create_foreign_key(
            "fk_routing_settings_updated_by",
            "routing_settings",
            "admin_users",
            ["updated_by"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- admin_audit_logs.created_at: add index ---
    if not _index_exists(conn, "ix_admin_audit_logs_created_at"):
        op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])

    # --- Composite indexes for routing hot path ---
    if not _index_exists(conn, "ix_pool_models_routing"):
        op.create_index("ix_pool_models_routing", "pool_models", ["pool_id", "is_enabled", "model_slug"])
    if not _index_exists(conn, "ix_pool_accounts_routing"):
        op.create_index("ix_pool_accounts_routing", "pool_accounts", ["pool_id", "status"])


def downgrade() -> None:
    # --- Drop composite indexes ---
    op.drop_index("ix_pool_accounts_routing", table_name="pool_accounts")
    op.drop_index("ix_pool_models_routing", table_name="pool_models")

    # --- admin_audit_logs.created_at: drop index ---
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")

    # --- routing_settings.updated_by: drop FK ---
    op.drop_constraint("fk_routing_settings_updated_by", "routing_settings", type_="foreignkey")

    # --- pool_accounts.created_by: revert to RESTRICT ---
    op.drop_constraint("fk_pool_accounts_created_by", "pool_accounts", type_="foreignkey")
    op.alter_column("pool_accounts", "created_by", existing_type=sa.BigInteger(), nullable=False)
    op.create_foreign_key(
        "pool_accounts_ibfk_2", "pool_accounts", "admin_users",
        ["created_by"], ["id"], ondelete="RESTRICT",
    )

    # --- pools.created_by: revert to RESTRICT ---
    op.drop_constraint("fk_pools_created_by", "pools", type_="foreignkey")
    op.alter_column("pools", "created_by", existing_type=sa.BigInteger(), nullable=False)
    op.create_foreign_key(
        "pools_ibfk_1", "pools", "admin_users",
        ["created_by"], ["id"], ondelete="RESTRICT",
    )

    # --- pool_accounts.status: SmallInteger -> String ---
    op.add_column("pool_accounts", sa.Column("status_old", sa.String(16), nullable=True))
    op.execute(
        "UPDATE pool_accounts SET status_old = CASE status "
        "WHEN 0 THEN 'active' "
        "WHEN 1 THEN 'disabled' "
        "WHEN 2 THEN 'exhausted' "
        "WHEN 3 THEN 'error' "
        "ELSE 'active' END"
    )
    op.alter_column("pool_accounts", "status_old", existing_type=sa.String(16), nullable=False)
    op.drop_constraint("chk_pool_accounts_status", "pool_accounts", type_="check")
    op.drop_column("pool_accounts", "status")
    op.alter_column("pool_accounts", "status_old", existing_type=sa.String(16), new_column_name="status")

    # --- admin_users.status: drop CHECK ---
    op.drop_constraint("chk_admin_users_status", "admin_users", type_="check")

    # --- admin_users.role: SmallInteger -> String ---
    op.add_column("admin_users", sa.Column("role_old", sa.String(20), nullable=True))
    op.execute(
        "UPDATE admin_users SET role_old = CASE role "
        "WHEN 0 THEN 'admin' "
        "WHEN 1 THEN 'super_admin' "
        "ELSE 'admin' END"
    )
    op.alter_column("admin_users", "role_old", existing_type=sa.String(20), nullable=False)
    op.drop_constraint("chk_admin_users_role", "admin_users", type_="check")
    op.drop_column("admin_users", "role")
    op.alter_column("admin_users", "role_old", existing_type=sa.String(20), new_column_name="role")
