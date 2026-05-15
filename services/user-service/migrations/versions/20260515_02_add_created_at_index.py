"""Add index on api_call_logs.created_at to fix sort buffer overflow.

MySQL error 1038 "Out of sort memory" occurs when ORDER BY created_at DESC
on the api_call_logs table exceeds sort_buffer_size. A descending index
allows the optimizer to use index-ordered scan instead of filesort.
"""

from __future__ import annotations

from alembic import op

revision = "20260515_02_add_created_at_index"
down_revision = "20260515_01_status_to_http_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_api_call_logs_created_at",
        "api_call_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_api_call_logs_created_at", table_name="api_call_logs")
