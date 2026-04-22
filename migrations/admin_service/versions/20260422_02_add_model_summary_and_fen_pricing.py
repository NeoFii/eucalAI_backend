"""Add model summary and fen-based pricing columns."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_02_add_model_summary_and_fen_pricing"
down_revision = "20260422_01_create_model_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("supported_models", sa.Column("summary", sa.String(length=255), nullable=True))
    op.add_column(
        "supported_models",
        sa.Column("price_input_per_m_fen", sa.Integer(), nullable=True),
    )
    op.add_column(
        "supported_models",
        sa.Column("price_output_per_m_fen", sa.Integer(), nullable=True),
    )

    bind.execute(
        sa.text(
            """
            UPDATE supported_models
            SET summary = :summary, description = :description
            WHERE slug = :slug
            """
        ),
        [
            {
                "slug": "deepseek-v3-2",
                "summary": "通用旗舰模型，兼顾聊天、代码与复杂任务执行。",
                "description": (
                    "DeepSeek-V3.2 是一款面向通用生产场景的旗舰模型，"
                    "在代码生成、长上下文问答和复杂任务执行之间保持均衡表现。"
                ),
            },
            {
                "slug": "deepseek-r1",
                "summary": "强化推理模型，适合数学、代码与多步骤规划。",
                "description": (
                    "DeepSeek-R1 聚焦推理与规划任务，"
                    "适合数学证明、代码推导和需要清晰中间步骤的复杂分析。"
                ),
            },
            {
                "slug": "gpt-4o",
                "summary": "多模态通用模型，适合实时交互与工具调用。",
                "description": (
                    "GPT-4o 提供文本、图像等多模态能力，"
                    "适合需要实时响应、工具协同和稳定通用表现的应用。"
                ),
            },
            {
                "slug": "claude-sonnet-4",
                "summary": "偏向代码与代理工作流的均衡模型。",
                "description": (
                    "Claude Sonnet 4 在代码理解、代理式工作流和长文档处理上表现稳健，"
                    "适合工程协作与复杂业务自动化。"
                ),
            },
        ],
    )


def downgrade() -> None:
    op.drop_column("supported_models", "price_output_per_m_fen")
    op.drop_column("supported_models", "price_input_per_m_fen")
    op.drop_column("supported_models", "summary")
