"""Create admin-owned model catalog tables."""

from __future__ import annotations

from alembic import op
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

revision = "20260422_01_create_model_catalog"
down_revision = "20260313_01_admin_baseline"
branch_labels = None
depends_on = None


def _catalog_tables() -> list[Table]:
    metadata = MetaData()
    model_vendors = Table(
        "model_vendors",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("slug", String(80), nullable=False, unique=True, index=True),
        Column("name", String(120), nullable=False),
        Column("logo_url", String(512), nullable=True),
        Column("is_active", Boolean, nullable=False, server_default=text("1")),
        Column("sort_order", Integer, nullable=False, server_default=text("0")),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    model_categories = Table(
        "model_categories",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("key", String(80), nullable=False, unique=True, index=True),
        Column("name", String(120), nullable=False),
        Column("sort_order", Integer, nullable=False, server_default=text("0")),
        Column("is_active", Boolean, nullable=False, server_default=text("1")),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    supported_models = Table(
        "supported_models",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("slug", String(120), nullable=False, unique=True, index=True),
        Column("name", String(160), nullable=False),
        Column(
            "vendor_id",
            BigInteger,
            ForeignKey("model_vendors.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        Column("description", Text, nullable=True),
        Column("capability_tags", JSON, nullable=False),
        Column("context_window", Integer, nullable=True),
        Column("max_output_tokens", Integer, nullable=True),
        Column("is_reasoning_model", Boolean, nullable=False, server_default=text("0")),
        Column("is_active", Boolean, nullable=False, server_default=text("1")),
        Column("sort_order", Integer, nullable=False, server_default=text("0")),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    supported_model_category_map = Table(
        "supported_model_category_map",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column(
            "model_id",
            BigInteger,
            ForeignKey("supported_models.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        Column(
            "category_id",
            BigInteger,
            ForeignKey("model_categories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        Column("sort_order", Integer, nullable=False, server_default=text("0")),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        UniqueConstraint("model_id", "category_id", name="uk_supported_model_category"),
    )
    return [
        model_vendors,
        model_categories,
        supported_models,
        supported_model_category_map,
    ]


def _execute_seed(sql: str) -> None:
    op.execute(text(sql))


def _seed_catalog() -> None:
    for slug, name, logo_url, sort_order in [
        ("deepseek", "DeepSeek", "/icons/providers/deepseek.png", 10),
        ("openai", "OpenAI", "/icons/providers/openai.png", 20),
        ("anthropic", "Anthropic", "/icons/providers/anthropic.png", 30),
        ("google", "Google", "/icons/providers/google.png", 40),
    ]:
        _execute_seed(
            f"""
            INSERT INTO model_vendors (slug, name, logo_url, is_active, sort_order)
            SELECT '{slug}', '{name}', '{logo_url}', 1, {sort_order}
            WHERE NOT EXISTS (SELECT 1 FROM model_vendors WHERE slug = '{slug}')
            """
        )

    for key, name, sort_order in [
        ("reasoning", "Reasoning", 1),
        ("coding", "Coding", 2),
        ("tool_use", "Tool use", 3),
        ("instruction_following", "Instruction following", 4),
    ]:
        _execute_seed(
            f"""
            INSERT INTO model_categories (`key`, name, sort_order, is_active)
            SELECT '{key}', '{name}', {sort_order}, 1
            WHERE NOT EXISTS (SELECT 1 FROM model_categories WHERE `key` = '{key}')
            """
        )

    models = [
        (
            "deepseek-v3-2",
            "DeepSeek-V3.2",
            "deepseek",
            "DeepSeek general-purpose chat model with strong coding capability.",
            '["chat","coding","reasoning"]',
            128000,
            8192,
            0,
            10,
            ["coding", "instruction_following"],
        ),
        (
            "deepseek-r1",
            "DeepSeek-R1",
            "deepseek",
            "DeepSeek reasoning model for math, code, and complex planning.",
            '["chat","reasoning","coding"]',
            128000,
            8192,
            1,
            20,
            ["reasoning", "coding"],
        ),
        (
            "gpt-4o",
            "GPT-4o",
            "openai",
            "OpenAI flagship multimodal model.",
            '["chat","vision","tool_calling"]',
            128000,
            16384,
            0,
            30,
            ["tool_use", "instruction_following"],
        ),
        (
            "claude-sonnet-4",
            "Claude Sonnet 4",
            "anthropic",
            "Anthropic balanced model for coding and agentic workflows.",
            '["chat","coding","tool_calling"]',
            200000,
            8192,
            0,
            40,
            ["coding", "tool_use", "instruction_following"],
        ),
    ]
    for slug, name, vendor_slug, description, tags, context, output, reasoning, order, categories in models:
        _execute_seed(
            f"""
            INSERT INTO supported_models (
                slug, name, vendor_id, description, capability_tags, context_window,
                max_output_tokens, is_reasoning_model, is_active, sort_order
            )
            SELECT
                '{slug}', '{name}', model_vendors.id, '{description}', '{tags}', {context},
                {output}, {reasoning}, 1, {order}
            FROM model_vendors
            WHERE model_vendors.slug = '{vendor_slug}'
              AND NOT EXISTS (SELECT 1 FROM supported_models WHERE slug = '{slug}')
            """
        )
        for index, category in enumerate(categories, start=1):
            _execute_seed(
                f"""
                INSERT INTO supported_model_category_map (model_id, category_id, sort_order)
                SELECT supported_models.id, model_categories.id, {index}
                FROM supported_models, model_categories
                WHERE supported_models.slug = '{slug}'
                  AND model_categories.`key` = '{category}'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM supported_model_category_map
                    WHERE model_id = supported_models.id
                      AND category_id = model_categories.id
                  )
                """
            )


def upgrade() -> None:
    bind = op.get_bind()
    for table in _catalog_tables():
        table.create(bind=bind, checkfirst=True)
    _seed_catalog()


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_catalog_tables()):
        table.drop(bind=bind, checkfirst=True)
