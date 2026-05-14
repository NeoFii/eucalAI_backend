"""Normalize pricing columns and add CHECK constraints.

Replaces `price_{dir}_per_m_fen` with `{dir}_price_per_million` to match
`pool_models` naming. Both store micro-yuan (1/1_000_000 CNY) per million
tokens. Also adds CHECK constraints ensuring active models have
routing_slug and pricing.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260514_normalize_price_columns"
down_revision = "20260505_02_system_rpm_cap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                ADD COLUMN `input_price_per_million` BIGINT NULL
                    COMMENT 'Input price per million tokens (micro-yuan)' AFTER `description`,
                ADD COLUMN `output_price_per_million` BIGINT NULL
                    COMMENT 'Output price per million tokens (micro-yuan)' AFTER `input_price_per_million`,
                ADD COLUMN `cached_input_price_per_million` BIGINT NULL
                    COMMENT 'Cached input price per million tokens (micro-yuan)' AFTER `output_price_per_million`
            """
        )
    )

    conn.execute(
        text(
            """
            UPDATE `supported_models` SET
                `input_price_per_million` = `price_input_per_m_fen`,
                `output_price_per_million` = `price_output_per_m_fen`,
                `cached_input_price_per_million` = `price_cached_input_per_m_fen`
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                DROP COLUMN `price_input_per_m_fen`,
                DROP COLUMN `price_output_per_m_fen`,
                DROP COLUMN `price_cached_input_per_m_fen`
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                ADD CONSTRAINT `chk_active_needs_routing_slug`
                CHECK (`is_active` = 0 OR `routing_slug` IS NOT NULL)
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                ADD CONSTRAINT `chk_active_needs_pricing`
                CHECK (
                    `is_active` = 0
                    OR (`input_price_per_million` IS NOT NULL AND `output_price_per_million` IS NOT NULL)
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                DROP CONSTRAINT `chk_active_needs_pricing`
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                DROP CONSTRAINT `chk_active_needs_routing_slug`
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                ADD COLUMN `price_input_per_m_fen` BIGINT NULL
                    COMMENT 'Input price per million tokens in micro-yuan' AFTER `description`,
                ADD COLUMN `price_output_per_m_fen` BIGINT NULL
                    COMMENT 'Output price per million tokens in micro-yuan' AFTER `price_input_per_m_fen`,
                ADD COLUMN `price_cached_input_per_m_fen` BIGINT NULL
                    COMMENT 'Cached input price per million tokens in micro-yuan' AFTER `price_output_per_m_fen`
            """
        )
    )

    conn.execute(
        text(
            """
            UPDATE `supported_models` SET
                `price_input_per_m_fen` = `input_price_per_million`,
                `price_output_per_m_fen` = `output_price_per_million`,
                `price_cached_input_per_m_fen` = `cached_input_price_per_million`
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE `supported_models`
                DROP COLUMN `input_price_per_million`,
                DROP COLUMN `output_price_per_million`,
                DROP COLUMN `cached_input_price_per_million`
            """
        )
    )
