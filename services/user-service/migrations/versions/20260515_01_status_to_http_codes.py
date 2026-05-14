"""Migrate api_call_logs.status from internal 0-4 codes to HTTP status codes.

Mapping:
  0 (pending)   → NULL (in-flight)
  1 (success)   → 200
  2 (error)     → mapped by error_code (402/400/429/502/503/428/500)
  3 (refunded)  → 200 (defensive, should be 0 rows)
  4 (aborted)   → 499
"""

from __future__ import annotations

from alembic import op

revision = "20260515_01_status_to_http_codes"
down_revision = "20260514_01_table_design_fixes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: widen column from TINYINT to SMALLINT first (TINYINT max=127, can't hold 200+)
    op.execute(
        "ALTER TABLE `api_call_logs` MODIFY COLUMN `status` SMALLINT DEFAULT 0 "
        "COMMENT 'status (migrating)'"
    )

    # Step 2: convert data
    op.execute("UPDATE `api_call_logs` SET `status` = 200 WHERE `status` = 1")
    op.execute("UPDATE `api_call_logs` SET `status` = 499 WHERE `status` = 4")
    op.execute(
        "UPDATE `api_call_logs` SET `status` = 402 "
        "WHERE `status` = 2 AND `error_code` = 'insufficient_balance'"
    )
    op.execute(
        "UPDATE `api_call_logs` SET `status` = 400 "
        "WHERE `status` = 2 AND `error_code` IN ('invalid_model', 'inference_validation')"
    )
    op.execute(
        "UPDATE `api_call_logs` SET `status` = 429 "
        "WHERE `status` = 2 AND `error_code` = 'channel_rate_limited'"
    )
    op.execute(
        "UPDATE `api_call_logs` SET `status` = 502 "
        "WHERE `status` = 2 AND `error_code` IN ('upstream_error', 'upstream_stream_error', 'inference_auth')"
    )
    op.execute(
        "UPDATE `api_call_logs` SET `status` = 503 "
        "WHERE `status` = 2 AND `error_code` = 'no_fallback'"
    )
    op.execute(
        "UPDATE `api_call_logs` SET `status` = 428 "
        "WHERE `status` = 2 AND `error_code` = 'pricing_not_configured'"
    )
    op.execute("UPDATE `api_call_logs` SET `status` = 500 WHERE `status` = 2")
    op.execute("UPDATE `api_call_logs` SET `status` = 200 WHERE `status` = 3")
    op.execute("UPDATE `api_call_logs` SET `status` = NULL WHERE `status` = 0")

    # Step 3: finalize column definition
    op.execute(
        "ALTER TABLE `api_call_logs` MODIFY COLUMN `status` SMALLINT DEFAULT NULL "
        "COMMENT 'HTTP status code: NULL=in-flight, 200=success, 4xx/5xx=error'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `api_call_logs` MODIFY COLUMN `status` SMALLINT DEFAULT 0 "
        "COMMENT 'Request status: 0=pending, 1=success, 2=error, 3=refunded, 4=aborted'"
    )
    op.execute("UPDATE `api_call_logs` SET `status` = 0 WHERE `status` IS NULL")
    op.execute("UPDATE `api_call_logs` SET `status` = 1 WHERE `status` = 200")
    op.execute("UPDATE `api_call_logs` SET `status` = 4 WHERE `status` = 499")
    op.execute("UPDATE `api_call_logs` SET `status` = 2 WHERE `status` >= 400")
