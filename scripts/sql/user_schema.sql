SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `users` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `uid` BIGINT NOT NULL COMMENT 'Public user UID',
    `email` VARCHAR(255) NOT NULL COMMENT 'Login email',
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'Password hash',
    `status` SMALLINT NOT NULL DEFAULT 1 COMMENT '0=disabled 1=active 2=pending',
    `email_verified_at` DATETIME NULL COMMENT 'Email verified at',
    `last_login_at` DATETIME NULL COMMENT 'Last login time',
    `last_login_ip` VARCHAR(45) NULL COMMENT 'Last login IP',
    `login_fail_count` INT NOT NULL DEFAULT 0 COMMENT 'Failed login count',
    `login_locked_until` DATETIME NULL COMMENT 'Login lock expiry',
    `balance` INT NOT NULL DEFAULT 0 COMMENT 'Available balance (分, 100=¥1)',
    `frozen_amount` INT NOT NULL DEFAULT 0 COMMENT 'Frozen balance in-flight (分)',
    `used_amount` INT NOT NULL DEFAULT 0 COMMENT 'Lifetime consumed (分)',
    `total_requests` INT NOT NULL DEFAULT 0 COMMENT 'Lifetime API-call count',
    `total_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Lifetime token count',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_users_uid` (`uid`),
    UNIQUE KEY `uk_users_email` (`email`),
    KEY `idx_users_status` (`status`),
    KEY `idx_users_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Users';

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
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_sessions_session_id` (`session_id`),
    UNIQUE KEY `uk_sessions_token_jti` (`token_jti`),
    KEY `idx_sessions_user_id` (`user_id`),
    KEY `idx_sessions_expires_at` (`expires_at`),
    KEY `idx_sessions_revoked_at` (`revoked_at`),
    CONSTRAINT `fk_sessions_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User sessions';

CREATE TABLE IF NOT EXISTS `email_verification_codes` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `email` VARCHAR(255) NOT NULL COMMENT 'Email',
    `code_hash` VARCHAR(255) NOT NULL COMMENT 'Verification code hash',
    `error_count` INT NOT NULL DEFAULT 0 COMMENT 'Error count',
    `purpose` VARCHAR(20) NOT NULL DEFAULT 'register' COMMENT 'register/reset_password/login',
    `expires_at` DATETIME NOT NULL COMMENT 'Expires at',
    `locked_until` DATETIME NULL COMMENT 'Rate-limit lock expiry',
    `used_at` DATETIME NULL COMMENT 'Used at',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    PRIMARY KEY (`id`),
    KEY `idx_codes_email` (`email`),
    KEY `idx_codes_email_purpose` (`email`, `purpose`),
    KEY `idx_codes_expires_at` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Email verification codes';

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
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_api_keys_key_hash` (`key_hash`),
    KEY `idx_user_api_keys_user_id` (`user_id`),
    KEY `idx_user_api_keys_status` (`status`),
    CONSTRAINT `fk_user_api_keys_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User API keys';

CREATE TABLE IF NOT EXISTS `user_vouchers` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=active 2=disabled',
    `original_amount` INT NOT NULL COMMENT 'Initial voucher amount (fen)',
    `remaining_amount` INT NOT NULL DEFAULT 0 COMMENT 'Unfrozen usable amount (fen)',
    `frozen_amount` INT NOT NULL DEFAULT 0 COMMENT 'Frozen amount (fen)',
    `used_amount` INT NOT NULL DEFAULT 0 COMMENT 'Consumed amount (fen)',
    `expires_at` DATETIME NULL COMMENT 'NULL = never expires',
    `created_by_admin_uid` BIGINT NULL COMMENT 'Creator admin uid',
    `remark` VARCHAR(255) NULL COMMENT 'Admin note',
    `deleted_at` DATETIME NULL COMMENT 'Soft deleted at',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    KEY `idx_user_vouchers_user_id` (`user_id`),
    KEY `idx_user_vouchers_status` (`status`),
    KEY `idx_user_vouchers_expires_at` (`expires_at`),
    KEY `idx_user_vouchers_admin_uid` (`created_by_admin_uid`),
    KEY `idx_user_vouchers_deleted_at` (`deleted_at`),
    CONSTRAINT `fk_user_vouchers_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User vouchers';

CREATE TABLE IF NOT EXISTS `voucher_transactions` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `voucher_id` BIGINT NOT NULL COMMENT 'FK user_vouchers.id',
    `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
    `type` TINYINT NOT NULL COMMENT '1=ISSUE 2=FREEZE 3=CONSUME 4=RELEASE 5=ADMIN_UPDATE 6=DELETE',
    `amount` INT NOT NULL COMMENT 'Voucher amount delta (fen)',
    `balance_before` INT NOT NULL COMMENT 'Remaining amount before change (fen)',
    `balance_after` INT NOT NULL COMMENT 'Remaining amount after change (fen)',
    `ref_type` VARCHAR(32) NULL COMMENT 'api_call / admin',
    `ref_id` VARCHAR(64) NULL COMMENT 'Related document id',
    `operator_id` BIGINT NULL COMMENT 'Admin uid when applicable',
    `remark` VARCHAR(255) NULL COMMENT 'Admin/system note',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    PRIMARY KEY (`id`),
    KEY `idx_voucher_tx_voucher_id` (`voucher_id`),
    KEY `idx_voucher_tx_user_id` (`user_id`),
    KEY `idx_voucher_tx_ref` (`ref_type`, `ref_id`),
    KEY `idx_voucher_tx_type_created` (`type`, `created_at`),
    CONSTRAINT `fk_voucher_tx_voucher_id` FOREIGN KEY (`voucher_id`) REFERENCES `user_vouchers` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_voucher_tx_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Voucher mutation ledger';

CREATE TABLE IF NOT EXISTS `balance_transactions` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
    `type` TINYINT NOT NULL COMMENT '1=TOPUP 2=CONSUME 3=REFUND 4=FREEZE 5=UNFREEZE 6=ADMIN_ADJUST',
    `amount` INT NOT NULL COMMENT 'Positive=increase, negative=decrease (分)',
    `balance_before` INT NOT NULL COMMENT 'balance snapshot before change (分)',
    `balance_after` INT NOT NULL COMMENT 'balance snapshot after change (分)',
    `ref_type` VARCHAR(32) NULL COMMENT 'topup_order / api_call',
    `ref_id` VARCHAR(64) NULL COMMENT 'related document id',
    `remark` VARCHAR(255) NULL COMMENT 'admin/system note',
    `operator_id` BIGINT NULL COMMENT 'admin uid when type=ADMIN_ADJUST',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_balance_tx_type_ref` (`type`, `ref_type`, `ref_id`),
    KEY `idx_balance_tx_user_created` (`user_id`, `created_at`),
    KEY `idx_balance_tx_type_created` (`type`, `created_at`),
    KEY `idx_balance_tx_ref` (`ref_type`, `ref_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Balance ledger (immutable append-only)';

CREATE TABLE IF NOT EXISTS `topup_orders` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `order_no` VARCHAR(64) NOT NULL COMMENT 'Business order no, TP{yyyyMMdd}{8rand}',
    `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
    `amount` INT NOT NULL COMMENT 'Top-up amount (分)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=pending 2=paid 3=cancelled 4=refunded',
    `payment_channel` VARCHAR(32) NOT NULL DEFAULT 'manual' COMMENT 'manual / alipay / wechat / stripe',
    `payment_no` VARCHAR(128) NULL COMMENT 'Third-party payment serial',
    `payment_raw` JSON NULL COMMENT 'Third-party callback raw payload',
    `paid_at` DATETIME NULL COMMENT 'Paid timestamp',
    `remark` VARCHAR(255) NULL COMMENT 'Admin note',
    `operator_id` BIGINT NULL COMMENT 'Admin uid for manual top-ups',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_topup_orders_order_no` (`order_no`),
    KEY `idx_topup_orders_user_created` (`user_id`, `created_at`),
    KEY `idx_topup_orders_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Top-up orders';

CREATE TABLE IF NOT EXISTS `api_call_logs` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `request_id` VARCHAR(64) NOT NULL COMMENT 'Global request id, spans 3-phase billing',
    `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
    `api_key_id` BIGINT NULL COMMENT 'FK user_api_keys.id, NULL if key not used',
    `model_name` VARCHAR(64) NOT NULL COMMENT 'Logical model name',
    `prompt_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Prompt tokens',
    `completion_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Completion tokens',
    `cached_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Cache-hit tokens',
    `total_tokens` INT NOT NULL DEFAULT 0 COMMENT 'prompt+completion+cached',
    `cost` INT NOT NULL DEFAULT 0 COMMENT 'User-side total charge (分)',
    `cost_detail` JSON NULL COMMENT 'Admin-only unit price breakdown',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=success 2=error 3=refunded',
    `duration_ms` INT NULL COMMENT 'Request latency (ms)',
    `is_stream` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '0=non-stream 1=stream',
    `ip` VARCHAR(45) NULL COMMENT 'Caller IP; gated by user record_ip setting',
    `error_code` VARCHAR(32) NULL COMMENT 'status=2 payload',
    `error_msg` VARCHAR(512) NULL COMMENT 'status=2 message',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_api_call_logs_request_id` (`request_id`),
    KEY `idx_api_call_logs_user_created` (`user_id`, `created_at`),
    KEY `idx_api_call_logs_key_created` (`api_key_id`, `created_at`),
    KEY `idx_api_call_logs_model_created` (`model_name`, `created_at`),
    KEY `idx_api_call_logs_status_created` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API call audit log written by router-service';

CREATE TABLE IF NOT EXISTS `usage_stats` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
    `api_key_id` BIGINT NULL COMMENT 'NULL = account-wide bucket',
    `account_api_key_id` BIGINT NOT NULL DEFAULT 0 COMMENT 'api_key_id with NULL represented as 0 for uniqueness',
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
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_usage_stats_bucket` (`user_id`, `api_key_id`, `model_name`, `stat_hour`),
    UNIQUE KEY `uk_usage_stats_bucket_effective` (`user_id`, `account_api_key_id`, `model_name`, `stat_hour`),
    KEY `idx_usage_stats_user_hour` (`user_id`, `stat_hour`),
    KEY `idx_usage_stats_key_hour` (`api_key_id`, `stat_hour`),
    KEY `idx_usage_stats_hour` (`stat_hour`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Hourly usage aggregates written by arq worker';

CREATE TABLE IF NOT EXISTS `invitation_release_outbox` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `code` VARCHAR(64) NOT NULL COMMENT 'Invitation code to release',
    `used_by_uid` BIGINT NOT NULL COMMENT 'Snowflake uid of the failed registrant',
    `retry_count` INT NOT NULL DEFAULT 0 COMMENT 'Worker retry counter',
    `last_error` VARCHAR(255) NULL COMMENT 'Last worker error message',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    KEY `idx_invitation_release_outbox_retry` (`retry_count`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Compensation outbox for failed invitation-code releases';

SET FOREIGN_KEY_CHECKS = 1;
