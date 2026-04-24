"""User service baseline — all tables with full indexes and constraints."""

from __future__ import annotations

from alembic import op

revision = "20260423_01_user_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `users` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `uid` VARCHAR(20) NOT NULL COMMENT 'Public user UID (NanoID)',
            `email` VARCHAR(255) NOT NULL COMMENT 'Login email',
            `password_hash` VARCHAR(255) NOT NULL COMMENT 'Password hash',
            `status` SMALLINT NOT NULL DEFAULT 1 COMMENT '0=disabled 1=active 2=pending',
            `email_verified_at` DATETIME NULL COMMENT 'Email verified at',
            `last_login_at` DATETIME NULL COMMENT 'Last login at',
            `last_login_ip` VARCHAR(45) NULL COMMENT 'Last login IP',
            `login_fail_count` INT NOT NULL DEFAULT 0 COMMENT 'Failed login count',
            `login_locked_until` DATETIME NULL COMMENT 'Login lock expiry',
            `balance` INT NOT NULL DEFAULT 0 COMMENT '可用余额（分，¥1=100）',
            `frozen_amount` INT NOT NULL DEFAULT 0 COMMENT '预冻结中的余额（分）',
            `used_amount` INT NOT NULL DEFAULT 0 COMMENT '历史累计消费（分）',
            `total_requests` INT NOT NULL DEFAULT 0 COMMENT '历史累计调用次数',
            `total_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT '历史累计 token 数',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_users_uid` (`uid`),
            UNIQUE KEY `uk_users_email` (`email`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Users'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `email_verification_codes` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
            `email` VARCHAR(255) NOT NULL COMMENT '邮箱地址',
            `code_hash` VARCHAR(255) NOT NULL COMMENT '验证码哈希',
            `purpose` VARCHAR(20) NOT NULL DEFAULT 'register' COMMENT '用途',
            `expires_at` DATETIME NOT NULL COMMENT '过期时间',
            `used_at` DATETIME NULL COMMENT '使用时间',
            `error_count` INT NOT NULL DEFAULT 0 COMMENT '错误次数',
            `locked_until` DATETIME NULL COMMENT '锁定截止时间',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            PRIMARY KEY (`id`),
            KEY `idx_codes_email` (`email`),
            KEY `idx_codes_expires_at` (`expires_at`),
            KEY `idx_codes_email_purpose` (`email`, `purpose`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Email verification codes'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `user_sessions` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `session_id` BIGINT NOT NULL COMMENT 'Public session id',
            `user_id` BIGINT NOT NULL COMMENT 'Owner user id',
            `token_jti` VARCHAR(64) NOT NULL COMMENT 'Refresh token jti hash',
            `refresh_token_hash` VARCHAR(255) NOT NULL COMMENT 'Refresh token hash',
            `user_agent` VARCHAR(512) NULL COMMENT 'User agent',
            `ip_address` VARCHAR(45) NULL COMMENT 'IP address',
            `expires_at` DATETIME NOT NULL COMMENT 'Expires at',
            `revoked_at` DATETIME NULL COMMENT 'Revoked at',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_user_sessions_session_id` (`session_id`),
            UNIQUE KEY `uk_user_sessions_token_jti` (`token_jti`),
            KEY `idx_user_sessions_user_id` (`user_id`),
            CONSTRAINT `fk_user_sessions_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='User sessions'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `user_api_keys` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `key_hash` VARCHAR(128) NOT NULL COMMENT 'SHA-256 of raw key',
            `key_prefix` VARCHAR(12) NOT NULL COMMENT 'First 8 plaintext chars for UI',
            `name` VARCHAR(100) NOT NULL COMMENT 'User-defined name',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=active 2=disabled 3=expired 4=exhausted',
            `quota_mode` TINYINT NOT NULL DEFAULT 1 COMMENT '1=unlimited 2=limited',
            `quota_limit` INT NOT NULL DEFAULT 0 COMMENT 'limited-mode cap (分)',
            `quota_used` INT NOT NULL DEFAULT 0 COMMENT 'cumulative spend via this key (分)',
            `allowed_models` TEXT NULL COMMENT 'comma-separated model names, NULL=all',
            `allow_ips` TEXT NULL COMMENT 'newline-separated CIDRs, NULL=all',
            `expires_at` DATETIME NULL COMMENT 'NULL = never expires',
            `last_used_at` DATETIME NULL COMMENT 'Last successful validation',
            `deleted_at` DATETIME NULL COMMENT 'Soft delete time',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_user_api_keys_key_hash` (`key_hash`),
            KEY `idx_user_api_keys_user_id` (`user_id`),
            KEY `idx_user_api_keys_status` (`status`),
            KEY `ix_user_api_keys_deleted_at` (`deleted_at`),
            CONSTRAINT `fk_user_api_keys_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='User API keys'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `balance_transactions` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `type` TINYINT NOT NULL COMMENT '1=TOPUP 2=CONSUME 3=REFUND 4=FREEZE 5=UNFREEZE 6=ADMIN_ADJUST 7=VOUCHER_REDEEM',
            `amount` INT NOT NULL COMMENT 'Positive=increase, negative=decrease (分)',
            `balance_before` INT NOT NULL COMMENT 'balance snapshot before change (分)',
            `balance_after` INT NOT NULL COMMENT 'balance snapshot after change (分)',
            `ref_type` VARCHAR(32) NULL COMMENT 'topup_order / api_call / voucher_code',
            `ref_id` VARCHAR(64) NULL COMMENT 'related document id',
            `remark` VARCHAR(255) NULL COMMENT 'admin/system note',
            `operator_id` BIGINT NULL COMMENT 'admin uid when type=ADMIN_ADJUST',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_balance_tx_type_ref` (`type`, `ref_type`, `ref_id`),
            KEY `idx_balance_tx_user_created` (`user_id`, `created_at`),
            KEY `idx_balance_tx_type_created` (`type`, `created_at`),
            KEY `idx_balance_tx_ref` (`ref_type`, `ref_id`),
            CONSTRAINT `fk_balance_transactions_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Balance ledger (immutable append-only)'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `topup_orders` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `order_no` VARCHAR(64) NOT NULL COMMENT 'Business order no',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `amount` INT NOT NULL COMMENT 'Top-up amount (分)',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=pending 2=paid 3=cancelled 4=refunded',
            `payment_channel` VARCHAR(32) NOT NULL DEFAULT 'manual'
                COMMENT 'manual / alipay / wechat / stripe',
            `payment_no` VARCHAR(128) NULL COMMENT 'Third-party payment serial',
            `payment_raw` JSON NULL COMMENT 'Third-party callback raw payload',
            `paid_at` DATETIME NULL COMMENT 'Paid timestamp',
            `remark` VARCHAR(255) NULL COMMENT 'Admin note',
            `operator_id` BIGINT NULL COMMENT 'Admin uid for manual top-ups',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_topup_orders_order_no` (`order_no`),
            KEY `idx_topup_orders_user_created` (`user_id`, `created_at`),
            KEY `idx_topup_orders_status` (`status`),
            CONSTRAINT `fk_topup_orders_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Top-up orders'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `api_call_logs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `request_id` VARCHAR(64) NOT NULL COMMENT 'Global request id',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `api_key_id` BIGINT NULL COMMENT 'FK user_api_keys.id',
            `model_name` VARCHAR(64) NOT NULL COMMENT 'Logical model name',
            `selected_model` VARCHAR(64) NULL COMMENT 'Routed model name',
            `provider_slug` VARCHAR(32) NULL COMMENT 'Provider identifier',
            `upstream_model` VARCHAR(64) NULL COMMENT 'Upstream provider model name',
            `config_version` INT NULL COMMENT 'Router config version',
            `config_source` VARCHAR(32) NULL COMMENT 'Config source',
            `inference_config_version` INT NULL COMMENT 'Inference config version',
            `inference_config_source` VARCHAR(32) NULL COMMENT 'Inference config source',
            `routing_tier` TINYINT NULL COMMENT 'Routing tier 1-5',
            `score_source` VARCHAR(32) NULL COMMENT 'Score source',
            `router_trace_id` VARCHAR(64) NULL COMMENT 'Router trace ID',
            `inference_error_code` VARCHAR(32) NULL COMMENT 'Inference service error code',
            `prompt_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Prompt tokens',
            `completion_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Completion tokens',
            `cached_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Cache-hit tokens',
            `total_tokens` INT NOT NULL DEFAULT 0 COMMENT 'prompt+completion+cached',
            `cost` INT NOT NULL DEFAULT 0 COMMENT 'User-side total charge (分)',
            `cost_detail` JSON NULL COMMENT 'Admin-only unit price breakdown',
            `status` TINYINT NOT NULL DEFAULT 0
                COMMENT '0=pending 1=success 2=error 3=refunded 4=aborted',
            `duration_ms` INT NULL COMMENT 'Request latency (ms)',
            `is_stream` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '0=non-stream 1=stream',
            `ip` VARCHAR(45) NULL COMMENT 'Caller IP',
            `error_code` VARCHAR(32) NULL COMMENT 'status=2 payload',
            `error_msg` VARCHAR(512) NULL COMMENT 'status=2 message',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_api_call_logs_request_id` (`request_id`),
            KEY `idx_api_call_logs_user_created` (`user_id`, `created_at`),
            KEY `idx_api_call_logs_key_created` (`api_key_id`, `created_at`),
            KEY `idx_api_call_logs_model_created` (`model_name`, `created_at`),
            KEY `idx_api_call_logs_status_created` (`status`, `created_at`),
            CONSTRAINT `fk_api_call_logs_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_api_call_logs_api_key_id`
                FOREIGN KEY (`api_key_id`) REFERENCES `user_api_keys` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='API call audit log'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `usage_stats` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `api_key_id` BIGINT NULL COMMENT 'NULL = account-wide bucket',
            `account_api_key_id` BIGINT NOT NULL DEFAULT 0
                COMMENT 'api_key_id with NULL represented as 0 for uniqueness',
            `model_name` VARCHAR(64) NOT NULL COMMENT 'Logical model name',
            `stat_hour` DATETIME NOT NULL COMMENT 'Aligned to the hour (UTC)',
            `request_count` INT NOT NULL DEFAULT 0 COMMENT 'Total calls',
            `success_count` INT NOT NULL DEFAULT 0 COMMENT 'status=1 calls',
            `error_count` INT NOT NULL DEFAULT 0 COMMENT 'status=2 calls',
            `prompt_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Prompt tokens sum',
            `completion_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Completion tokens sum',
            `cached_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Cache-hit tokens sum',
            `total_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Total tokens sum',
            `total_cost` INT NOT NULL DEFAULT 0 COMMENT 'Total cost (分)',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_usage_stats_bucket` (`user_id`, `api_key_id`, `model_name`, `stat_hour`),
            UNIQUE KEY `uk_usage_stats_bucket_effective`
                (`user_id`, `account_api_key_id`, `model_name`, `stat_hour`),
            KEY `idx_usage_stats_user_hour` (`user_id`, `stat_hour`),
            KEY `idx_usage_stats_key_hour` (`api_key_id`, `stat_hour`),
            KEY `idx_usage_stats_hour` (`stat_hour`),
            CONSTRAINT `fk_usage_stats_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_usage_stats_api_key_id`
                FOREIGN KEY (`api_key_id`) REFERENCES `user_api_keys` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Hourly usage aggregates'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `voucher_redemption_codes` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `code_hash` VARCHAR(64) NOT NULL COMMENT 'SHA-256 hash of normalized code',
            `code_prefix` VARCHAR(8) NOT NULL COMMENT 'Non-secret display prefix',
            `code_suffix` VARCHAR(8) NOT NULL COMMENT 'Non-secret display suffix',
            `amount` INT NOT NULL COMMENT 'Redeem amount (fen)',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=active 2=redeemed 3=disabled',
            `starts_at` DATETIME NOT NULL COMMENT 'Code validity start',
            `expires_at` DATETIME NOT NULL COMMENT 'Code validity end',
            `redeemed_user_id` BIGINT NULL COMMENT 'Redeeming users.id',
            `redeemed_at` DATETIME NULL COMMENT 'Redeemed at',
            `created_by_admin_uid` VARCHAR(20) NULL COMMENT 'Creator admin uid (NanoID)',
            `remark` VARCHAR(255) NULL COMMENT 'Admin note',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_voucher_codes_code_hash` (`code_hash`),
            KEY `idx_voucher_codes_status` (`status`),
            KEY `idx_voucher_codes_starts_at` (`starts_at`),
            KEY `idx_voucher_codes_expires_at` (`expires_at`),
            KEY `idx_voucher_codes_redeemed_user` (`redeemed_user_id`),
            KEY `idx_voucher_codes_admin_uid` (`created_by_admin_uid`),
            CONSTRAINT `fk_voucher_codes_redeemed_user_id`
                FOREIGN KEY (`redeemed_user_id`) REFERENCES `users` (`id`)
                ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Voucher redemption codes'
        """
    )


def downgrade() -> None:
    for table in [
        "voucher_redemption_codes", "usage_stats", "api_call_logs",
        "topup_orders", "balance_transactions", "user_api_keys",
        "user_sessions", "email_verification_codes", "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS `{table}`")
