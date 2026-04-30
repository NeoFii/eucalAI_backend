"""Monetary precision upgrade: INT fen -> BIGINT micro-yuan (1 yuan = 1,000,000)."""

from __future__ import annotations

from alembic import op

revision = "20260430_09_monetary_precision"
down_revision = "20260429_08_routing_slug"
branch_labels = None
depends_on = None

_MULTIPLIER = 10_000  # 1 fen = 10,000 micro-yuan


def upgrade() -> None:
    # supported_models
    for col in ("price_input_per_m_fen", "price_output_per_m_fen", "price_cached_input_per_m_fen"):
        op.execute(f"ALTER TABLE `supported_models` MODIFY COLUMN `{col}` BIGINT NULL")
        op.execute(f"UPDATE `supported_models` SET `{col}` = `{col}` * {_MULTIPLIER} WHERE `{col}` IS NOT NULL")

    # pool_models
    for col in ("input_price_per_million", "output_price_per_million"):
        op.execute(f"ALTER TABLE `pool_models` MODIFY COLUMN `{col}` BIGINT NOT NULL DEFAULT 0")
        op.execute(f"UPDATE `pool_models` SET `{col}` = `{col}` * {_MULTIPLIER}")
    op.execute(f"ALTER TABLE `pool_models` MODIFY COLUMN `cached_input_price_per_million` BIGINT NULL")
    op.execute(f"UPDATE `pool_models` SET `cached_input_price_per_million` = `cached_input_price_per_million` * {_MULTIPLIER} WHERE `cached_input_price_per_million` IS NOT NULL")

    # pool_accounts
    op.execute(f"ALTER TABLE `pool_accounts` MODIFY COLUMN `balance` BIGINT NOT NULL DEFAULT 0")
    op.execute(f"UPDATE `pool_accounts` SET `balance` = `balance` * {_MULTIPLIER}")


def downgrade() -> None:
    # pool_accounts
    op.execute(f"UPDATE `pool_accounts` SET `balance` = `balance` / {_MULTIPLIER}")
    op.execute("ALTER TABLE `pool_accounts` MODIFY COLUMN `balance` INT NOT NULL DEFAULT 0")

    # pool_models
    op.execute(f"UPDATE `pool_models` SET `cached_input_price_per_million` = `cached_input_price_per_million` / {_MULTIPLIER} WHERE `cached_input_price_per_million` IS NOT NULL")
    op.execute("ALTER TABLE `pool_models` MODIFY COLUMN `cached_input_price_per_million` INT NULL")
    for col in ("output_price_per_million", "input_price_per_million"):
        op.execute(f"UPDATE `pool_models` SET `{col}` = `{col}` / {_MULTIPLIER}")
        op.execute(f"ALTER TABLE `pool_models` MODIFY COLUMN `{col}` INT NOT NULL DEFAULT 0")

    # supported_models
    for col in ("price_cached_input_per_m_fen", "price_output_per_m_fen", "price_input_per_m_fen"):
        op.execute(f"UPDATE `supported_models` SET `{col}` = `{col}` / {_MULTIPLIER} WHERE `{col}` IS NOT NULL")
        op.execute(f"ALTER TABLE `supported_models` MODIFY COLUMN `{col}` INT NULL")
