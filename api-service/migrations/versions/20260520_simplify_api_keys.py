"""Drop redundant API key fields: quota, models, IPs, expiry.

Key is now a pure service credential. Quota control lives at user.balance level.

Revision ID: 20260520_simplify_api_keys
Revises: 20260520_upgrade_call_logs
"""

from alembic import op

revision = "20260520_simplify_api_keys"
down_revision = "20260520_upgrade_call_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("user_api_keys", "quota_mode")
    op.drop_column("user_api_keys", "quota_limit")
    op.drop_column("user_api_keys", "quota_used")
    op.drop_column("user_api_keys", "allowed_models")
    op.drop_column("user_api_keys", "allow_ips")
    op.drop_column("user_api_keys", "expires_at")


def downgrade() -> None:
    from sqlalchemy import BigInteger, Column, DateTime, SmallInteger, Text

    op.add_column("user_api_keys", Column("quota_mode", SmallInteger, nullable=False, server_default="1"))
    op.add_column("user_api_keys", Column("quota_limit", BigInteger, nullable=False, server_default="0"))
    op.add_column("user_api_keys", Column("quota_used", BigInteger, nullable=False, server_default="0"))
    op.add_column("user_api_keys", Column("allowed_models", Text, nullable=True))
    op.add_column("user_api_keys", Column("allow_ips", Text, nullable=True))
    op.add_column("user_api_keys", Column("expires_at", DateTime, nullable=True))
