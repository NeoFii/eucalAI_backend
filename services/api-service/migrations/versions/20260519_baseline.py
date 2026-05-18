"""Consolidated baseline — all 22 tables for the merged api-service database."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260519_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # User-domain tables (9)
    # =========================================================================

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
            `balance` BIGINT NOT NULL DEFAULT 0 COMMENT '可用余额（微元，¥1=1000000）',
            `frozen_amount` BIGINT NOT NULL DEFAULT 0 COMMENT '预冻结中的余额（微元）',
            `used_amount` BIGINT NOT NULL DEFAULT 0 COMMENT '历史累计消费（微元）',
            `total_requests` INT NOT NULL DEFAULT 0 COMMENT '历史累计调用次数',
            `total_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT '历史累计 token 数',
            `rpm_limit` INT NULL DEFAULT NULL COMMENT '用户级每分钟请求上限，NULL=用全局默认',
            `record_ip_log` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '用户是否允许记录 IP',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_users_uid` (`uid`),
            UNIQUE KEY `uk_users_email` (`email`),
            CONSTRAINT `chk_balance_non_negative` CHECK (`balance` >= 0),
            CONSTRAINT `chk_frozen_non_negative` CHECK (`frozen_amount` >= 0)
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
            KEY `idx_user_sessions_expires_at` (`expires_at`),
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
            `quota_limit` BIGINT NOT NULL DEFAULT 0 COMMENT 'limited-mode cap (micro-yuan)',
            `quota_used` BIGINT NOT NULL DEFAULT 0 COMMENT 'cumulative spend via this key (micro-yuan)',
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
            `amount` BIGINT NOT NULL COMMENT 'Positive=increase, negative=decrease (micro-yuan)',
            `balance_before` BIGINT NOT NULL COMMENT 'balance snapshot before change (micro-yuan)',
            `balance_after` BIGINT NOT NULL COMMENT 'balance snapshot after change (micro-yuan)',
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
            `amount` BIGINT NOT NULL COMMENT 'Top-up amount (micro-yuan)',
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

    # api_call_logs — refactored structure (14 core columns + log_type + other)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `api_call_logs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `request_id` VARCHAR(64) NOT NULL COMMENT 'Global request id',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `api_key_id` BIGINT NULL COMMENT 'FK user_api_keys.id',
            `model_name` VARCHAR(64) NOT NULL COMMENT 'Logical model name',
            `log_type` SMALLINT NOT NULL DEFAULT 0
                COMMENT '0=Unknown 1=Topup 2=Consume 3=Manage 4=System 5=Error 6=Refund',
            `prompt_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Prompt tokens',
            `completion_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Completion tokens',
            `quota` BIGINT NOT NULL DEFAULT 0 COMMENT 'User-side total charge (micro-yuan)',
            `duration_ms` INT NULL COMMENT 'Request latency (ms)',
            `is_stream` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '0=non-stream 1=stream',
            `ip` VARCHAR(45) NULL COMMENT 'Caller IP',
            `other` JSON NULL COMMENT 'Extensible metadata JSON',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_api_call_logs_request_id` (`request_id`),
            KEY `idx_api_call_logs_user_created` (`user_id`, `created_at`),
            KEY `idx_api_call_logs_key_created` (`api_key_id`, `created_at`),
            KEY `idx_api_call_logs_model_created` (`model_name`, `created_at`),
            KEY `idx_api_call_logs_created_at` (`created_at`),
            KEY `idx_api_call_logs_log_type` (`log_type`),
            KEY `idx_api_call_logs_user_id` (`user_id`),
            KEY `idx_api_call_logs_api_key_id` (`api_key_id`),
            KEY `idx_api_call_logs_model_name` (`model_name`),
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
            `total_cost` BIGINT NOT NULL DEFAULT 0 COMMENT 'Total cost (micro-yuan)',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
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
            `amount` BIGINT NOT NULL COMMENT 'Redeem amount (micro-yuan)',
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

    # =========================================================================
    # Admin-domain tables (13)
    # =========================================================================

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `admin_users` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `uid` VARCHAR(20) NOT NULL COMMENT 'Public admin UID (NanoID)',
            `email` VARCHAR(255) NOT NULL COMMENT 'Login email',
            `password_hash` VARCHAR(255) NOT NULL COMMENT 'Password hash',
            `name` VARCHAR(100) NOT NULL COMMENT 'Admin display name',
            `status` SMALLINT NOT NULL DEFAULT 1 COMMENT '0=disabled 1=active',
            `role` SMALLINT NOT NULL DEFAULT 0 COMMENT '0=admin 1=super_admin',
            `is_root` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '根管理员标记',
            `created_by_admin_id` BIGINT NULL COMMENT 'Creator admin id',
            `updated_by_admin_id` BIGINT NULL COMMENT 'Last updater admin id',
            `password_changed_at` DATETIME NULL COMMENT 'Last password change time',
            `password_changed_by_admin_id` BIGINT NULL COMMENT 'Last password changer admin id',
            `last_login_at` DATETIME NULL COMMENT 'Last login time',
            `last_login_ip` VARCHAR(45) NULL COMMENT 'Last login IP',
            `login_fail_count` INT NOT NULL DEFAULT 0 COMMENT 'Failed login count',
            `login_locked_until` DATETIME NULL COMMENT 'Login lock expiry',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_admin_users_uid` (`uid`),
            UNIQUE KEY `uk_admin_users_email` (`email`),
            CONSTRAINT `fk_admin_users_created_by`
                FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `fk_admin_users_updated_by`
                FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `fk_admin_users_pw_changed_by`
                FOREIGN KEY (`password_changed_by_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `chk_admin_users_role` CHECK (`role` IN (0, 1)),
            CONSTRAINT `chk_admin_users_status` CHECK (`status` IN (0, 1))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Admin users'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `audit_action_definitions` (
            `code` VARCHAR(100) NOT NULL COMMENT 'Action code primary key',
            `label` VARCHAR(120) NOT NULL COMMENT 'Display label',
            `category` VARCHAR(32) NOT NULL COMMENT 'Action category',
            `resource_type` VARCHAR(50) NOT NULL COMMENT 'Resource type',
            `description` VARCHAR(255) NULL COMMENT 'Optional description',
            `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether action is active',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            `updated_by` BIGINT NULL COMMENT 'Last updater admin id',
            PRIMARY KEY (`code`),
            CONSTRAINT `fk_audit_action_defs_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `chk_audit_category` CHECK (`category` IN ('governance','auth','user_management','model_catalog','routing_config','voucher','pool','unknown'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Audit action definitions registry'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `admin_audit_logs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `actor_admin_id` BIGINT NULL COMMENT 'Actor admin id',
            `target_admin_id` BIGINT NULL COMMENT 'Target admin id',
            `action` VARCHAR(100) NOT NULL COMMENT 'Operation code',
            `resource_type` VARCHAR(50) NOT NULL COMMENT 'Resource type',
            `resource_id` VARCHAR(100) NULL COMMENT 'Resource identifier',
            `status` VARCHAR(20) NOT NULL COMMENT 'success/failed',
            `before_data` JSON NULL COMMENT 'Data before change',
            `after_data` JSON NULL COMMENT 'Data after change',
            `reason` VARCHAR(255) NULL COMMENT 'Reason or failure summary',
            `ip_address` VARCHAR(45) NULL COMMENT 'Source IP',
            `user_agent` VARCHAR(512) NULL COMMENT 'Source user agent',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Event time',
            PRIMARY KEY (`id`),
            KEY `idx_audit_logs_actor` (`actor_admin_id`),
            KEY `idx_audit_logs_target` (`target_admin_id`),
            KEY `idx_audit_logs_action` (`action`),
            KEY `idx_audit_logs_resource_type` (`resource_type`),
            KEY `ix_admin_audit_logs_created_at` (`created_at`),
            CONSTRAINT `fk_audit_logs_actor`
                FOREIGN KEY (`actor_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `fk_audit_logs_target`
                FOREIGN KEY (`target_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `fk_audit_logs_action`
                FOREIGN KEY (`action`) REFERENCES `audit_action_definitions` (`code`)
                ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Admin audit logs (append-only)'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `model_vendors` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `slug` VARCHAR(80) NOT NULL COMMENT 'Vendor slug',
            `name` VARCHAR(120) NOT NULL COMMENT 'Vendor display name',
            `logo_url` VARCHAR(512) NULL COMMENT 'Vendor logo URL',
            `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether vendor is active',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_model_vendors_slug` (`slug`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Model vendors'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `model_categories` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `key` VARCHAR(80) NOT NULL COMMENT 'Category key',
            `name` VARCHAR(120) NOT NULL COMMENT 'Category display name',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
            `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether category is active',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_model_categories_key` (`key`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Model categories'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `model_catalog` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `slug` VARCHAR(120) NOT NULL COMMENT 'Model slug',
            `routing_slug` VARCHAR(200) NULL COMMENT '路由用 slug，对应 pool_model_configs.model_slug',
            `name` VARCHAR(160) NOT NULL COMMENT 'Model display name',
            `vendor_id` BIGINT NOT NULL COMMENT 'Model vendor id',
            `summary` VARCHAR(255) NULL COMMENT 'Model card summary',
            `description` TEXT NULL COMMENT 'Model detail description',
            `sale_input_per_million` BIGINT NULL COMMENT 'Sale input price per million tokens (micro-yuan)',
            `sale_output_per_million` BIGINT NULL COMMENT 'Sale output price per million tokens (micro-yuan)',
            `sale_cached_input_per_million` BIGINT NULL COMMENT 'Sale cached input price per million tokens (micro-yuan)',
            `capability_tags` JSON NOT NULL COMMENT 'Capability tag list',
            `context_window` INT NULL COMMENT 'Context window tokens',
            `max_output_tokens` INT NULL COMMENT 'Max output tokens',
            `is_reasoning_model` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether this is a reasoning model',
            `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether model is active',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_model_catalog_slug` (`slug`),
            UNIQUE KEY `uk_model_catalog_routing_slug` (`routing_slug`),
            KEY `idx_model_catalog_vendor_id` (`vendor_id`),
            CONSTRAINT `fk_model_catalog_vendor_id`
                FOREIGN KEY (`vendor_id`) REFERENCES `model_vendors` (`id`)
                ON DELETE RESTRICT,
            CONSTRAINT `chk_active_needs_routing_slug` CHECK (`is_active` = 0 OR `routing_slug` IS NOT NULL),
            CONSTRAINT `chk_active_needs_pricing` CHECK (`is_active` = 0 OR (`sale_input_per_million` IS NOT NULL AND `sale_output_per_million` IS NOT NULL))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Model catalog'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `model_catalog_category_map` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `model_id` BIGINT NOT NULL COMMENT 'Model catalog id',
            `category_id` BIGINT NOT NULL COMMENT 'Model category id',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Model-local category order',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_model_catalog_category` (`model_id`, `category_id`),
            KEY `idx_model_category_map_model_id` (`model_id`),
            KEY `idx_model_category_map_category_id` (`category_id`),
            CONSTRAINT `fk_model_category_map_model_id`
                FOREIGN KEY (`model_id`) REFERENCES `model_catalog` (`id`)
                ON DELETE CASCADE,
            CONSTRAINT `fk_model_category_map_category_id`
                FOREIGN KEY (`category_id`) REFERENCES `model_categories` (`id`)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Model catalog to category mapping'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `routing_configs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `version` INT NOT NULL COMMENT 'Monotonic version number',
            `status` VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT 'draft / active / superseded',
            `config_data` JSON NOT NULL COMMENT 'Full routing policy JSON',
            `description` VARCHAR(512) NULL COMMENT 'Version description',
            `published_at` DATETIME NULL COMMENT 'When this version was published',
            `published_by` BIGINT NULL COMMENT 'Admin who published this version',
            `created_by` BIGINT NOT NULL COMMENT 'Admin who created this version',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_routing_configs_version` (`version`),
            KEY `idx_routing_configs_status` (`status`),
            CONSTRAINT `fk_routing_configs_published_by`
                FOREIGN KEY (`published_by`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL,
            CONSTRAINT `fk_routing_configs_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`)
                ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Routing configs'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `provider_credentials` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `slug` VARCHAR(64) NOT NULL COMMENT 'Reference identifier',
            `provider_slug` VARCHAR(64) NOT NULL COMMENT 'Provider identifier e.g. autodl',
            `api_key_enc` JSON NOT NULL COMMENT 'AES-256-GCM encrypted {ciphertext,iv,tag}',
            `mask` VARCHAR(32) NOT NULL COMMENT 'Masked display e.g. sk-1****89ab',
            `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether credential is usable',
            `remark` VARCHAR(256) NULL COMMENT 'Optional note',
            `created_by` BIGINT NOT NULL COMMENT 'Admin who created this credential',
            `updated_by` BIGINT NULL COMMENT 'Admin who last updated this credential',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_provider_credentials_slug` (`slug`),
            CONSTRAINT `fk_provider_credentials_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`)
                ON DELETE RESTRICT,
            CONSTRAINT `fk_provider_credentials_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`)
                ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Provider credentials'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `routing_settings` (
            `key` VARCHAR(64) NOT NULL COMMENT '配置键',
            `value` TEXT NOT NULL COMMENT '配置值',
            `value_type` VARCHAR(16) NOT NULL DEFAULT 'string' COMMENT 'string/float/int',
            `group_name` VARCHAR(32) NOT NULL COMMENT 'general/weights/score_bands/tier_model_map/rate_limits',
            `label` VARCHAR(128) NOT NULL COMMENT '管理端显示名',
            `description` VARCHAR(512) NULL,
            `sort_order` INT NOT NULL DEFAULT 0,
            `updated_by` BIGINT NULL,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`key`),
            KEY `idx_routing_settings_group` (`group_name`),
            CONSTRAINT `fk_routing_settings_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='路由策略 key-value 配置'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `pools` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `slug` VARCHAR(64) NOT NULL COMMENT '引用标识',
            `name` VARCHAR(128) NOT NULL COMMENT '显示名称',
            `base_url` VARCHAR(512) NOT NULL COMMENT '平台统一请求地址',
            `is_enabled` TINYINT(1) NOT NULL DEFAULT 1,
            `priority` INT NOT NULL DEFAULT 0 COMMENT '路由优先级，越大越优先',
            `weight` INT NOT NULL DEFAULT 1 COMMENT '路由权重',
            `health_check_endpoint` VARCHAR(512) NULL COMMENT '余额/状态检查接口',
            `remark` VARCHAR(256) NULL,
            `created_by` BIGINT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_pools_slug` (`slug`),
            KEY `idx_pools_enabled` (`is_enabled`),
            CONSTRAINT `fk_pools_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_pools_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `pool_model_configs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `pool_id` BIGINT NOT NULL,
            `model_slug` VARCHAR(120) NOT NULL COMMENT '系统模型标识',
            `upstream_model_id` VARCHAR(200) NOT NULL COMMENT '上游实际模型 ID',
            `cost_input_per_million` BIGINT NOT NULL DEFAULT 0 COMMENT '每百万输入 token 成本价 (micro-yuan)',
            `cost_output_per_million` BIGINT NOT NULL DEFAULT 0 COMMENT '每百万输出 token 成本价 (micro-yuan)',
            `cost_cached_input_per_million` BIGINT NULL COMMENT '缓存命中输入成本价 (micro-yuan)',
            `context_length` INT NULL COMMENT '该平台对此模型的最大上下文长度',
            `is_enabled` TINYINT(1) NOT NULL DEFAULT 1,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_pool_model` (`pool_id`, `model_slug`),
            KEY `ix_pool_model_configs_routing` (`pool_id`, `is_enabled`, `model_slug`),
            CONSTRAINT `fk_pool_model_configs_pool`
                FOREIGN KEY (`pool_id`) REFERENCES `pools` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `pool_accounts` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `pool_id` BIGINT NOT NULL,
            `name` VARCHAR(128) NOT NULL COMMENT '备注名',
            `api_key_enc` JSON NOT NULL COMMENT 'AES-256-GCM encrypted {ciphertext,iv,tag}',
            `mask` VARCHAR(32) NOT NULL COMMENT '脱敏显示',
            `balance` BIGINT NOT NULL DEFAULT 0 COMMENT '余额 (micro-yuan)',
            `status` SMALLINT NOT NULL DEFAULT 0 COMMENT '0=active 1=disabled 2=exhausted 3=error',
            `rpm_limit` INT NULL COMMENT '每分钟请求上限',
            `tpm_limit` INT NULL COMMENT '每分钟 token 上限',
            `weight` INT NOT NULL DEFAULT 1 COMMENT '轮转权重',
            `last_checked_at` DATETIME NULL COMMENT '上次检查时间',
            `last_health_check_error` VARCHAR(512) NULL COMMENT '上次健康检查错误信息',
            `remark` VARCHAR(256) NULL,
            `created_by` BIGINT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            KEY `idx_pool_accounts_pool` (`pool_id`),
            KEY `idx_pool_accounts_status` (`status`),
            KEY `ix_pool_accounts_routing` (`pool_id`, `status`),
            CONSTRAINT `fk_pool_accounts_pool`
                FOREIGN KEY (`pool_id`) REFERENCES `pools` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_pool_accounts_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_pool_accounts_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
            CONSTRAINT `chk_pool_accounts_status` CHECK (`status` IN (0, 1, 2, 3)),
            CONSTRAINT `chk_balance_non_negative` CHECK (`balance` >= 0)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    # =========================================================================
    # Seed data
    # =========================================================================
    _seed_data()


def _seed_data() -> None:
    """Insert initial reference data for model_vendors, model_categories, and audit_action_definitions."""
    conn = op.get_bind()

    # model_vendors
    conn.execute(text(
        "INSERT INTO `model_vendors` (`slug`, `name`, `logo_url`, `is_active`, `sort_order`) VALUES "
        "('deepseek', 'DeepSeek', '/icons/providers/deepseek.png', 1, 10), "
        "('openai', 'OpenAI', '/icons/providers/openai.png', 1, 20), "
        "('anthropic', 'Anthropic', '/icons/providers/anthropic.png', 1, 30), "
        "('google', 'Google', '/icons/providers/google.png', 1, 40)"
    ))

    # model_categories
    conn.execute(text(
        "INSERT INTO `model_categories` (`key`, `name`, `sort_order`, `is_active`) VALUES "
        "('reasoning', 'Reasoning', 1, 1), "
        "('coding', 'Coding', 2, 1), "
        "('tool_use', 'Tool use', 3, 1), "
        "('instruction_following', 'Instruction following', 4, 1)"
    ))

    # audit_action_definitions
    _seed_audit_actions(conn)


def _seed_audit_actions(conn) -> None:
    """Seed audit_action_definitions with all known action codes."""
    actions = [
        ("bootstrap_super_admin", "初始化超级管理员", "governance", "admin_user", 0),
        ("create_admin", "创建管理员", "governance", "admin_user", 1),
        ("enable_admin", "启用管理员", "governance", "admin_user", 2),
        ("disable_admin", "禁用管理员", "governance", "admin_user", 3),
        ("reset_admin_password", "重置管理员密码", "governance", "admin_user", 4),
        ("update_admin_role", "更新管理员角色", "governance", "admin_user", 5),
        ("admin_login_success", "管理员登录成功", "auth", "admin_user", 6),
        ("admin_login_failed", "管理员登录失败", "auth", "admin_user", 7),
        ("admin_login_locked", "管理员账号锁定", "auth", "admin_user", 8),
        ("admin_login_unlocked", "管理员账号解锁", "auth", "admin_user", 9),
        ("admin_change_password", "管理员修改密码", "auth", "admin_user", 10),
        ("enable_user", "启用用户", "user_management", "user", 11),
        ("disable_user", "禁用用户", "user_management", "user", 12),
        ("reset_user_password", "重置用户密码", "user_management", "user", 13),
        ("topup_user", "用户充值", "user_management", "user", 14),
        ("adjust_user_balance", "调整用户余额", "user_management", "user", 15),
        ("disable_user_api_key", "禁用用户API密钥", "user_management", "user", 16),
        ("enable_user_api_key", "启用用户API密钥", "user_management", "user", 17),
        ("update_user_rpm", "更新用户速率限制", "user_management", "user", 18),
        ("create_model_vendor", "创建模型厂商", "model_catalog", "model_vendor", 19),
        ("update_model_vendor", "更新模型厂商", "model_catalog", "model_vendor", 20),
        ("create_model_category", "创建模型分类", "model_catalog", "model_category", 21),
        ("update_model_category", "更新模型分类", "model_catalog", "model_category", 22),
        ("create_supported_model", "创建支持模型", "model_catalog", "supported_model", 23),
        ("update_supported_model", "更新支持模型", "model_catalog", "supported_model", 24),
        ("archive_supported_model", "归档支持模型", "model_catalog", "supported_model", 25),
        ("disable_supported_model", "归档支持模型", "model_catalog", "supported_model", 26),
        ("create_routing_config", "创建路由配置", "routing_config", "routing_config", 27),
        ("update_routing_config", "更新路由配置", "routing_config", "routing_config", 28),
        ("publish_routing_config", "发布路由配置", "routing_config", "routing_config", 29),
        ("rollback_routing_config", "回滚路由配置", "routing_config", "routing_config", 30),
        ("create_provider_credential", "创建供应商凭证", "routing_config", "routing_config", 31),
        ("update_provider_credential", "更新供应商凭证", "routing_config", "routing_config", 32),
        ("disable_provider_credential", "禁用供应商凭证", "routing_config", "routing_config", 33),
        ("force_disable_provider_credential", "强制禁用供应商凭证", "routing_config", "routing_config", 34),
        ("update_routing_setting", "更新路由设置", "routing_config", "routing_setting", 35),
        ("batch_update_routing_settings", "批量更新路由设置", "routing_config", "routing_setting", 36),
        ("generate_voucher_codes", "生成兑换码", "voucher", "voucher", 37),
        ("disable_voucher_code", "禁用兑换码", "voucher", "voucher", 38),
        ("create_pool", "创建资源池", "pool", "pool", 39),
        ("update_pool", "更新资源池", "pool", "pool", 40),
        ("disable_pool", "禁用资源池", "pool", "pool", 41),
        ("add_pool_model", "添加池模型", "pool", "pool_model", 42),
        ("update_pool_model", "更新池模型", "pool", "pool_model", 43),
        ("remove_pool_model", "移除池模型", "pool", "pool_model", 44),
        ("add_pool_account", "添加池账号", "pool", "pool_account", 45),
        ("update_pool_account", "更新池账号", "pool", "pool_account", 46),
        ("disable_pool_account", "禁用池账号", "pool", "pool_account", 47),
        ("sync_pool_models", "同步池模型", "pool", "pool", 48),
        ("check_pool_balances", "检查池余额", "pool", "pool", 49),
    ]
    for code, label, category, resource_type, sort_order in actions:
        conn.execute(text(
            "INSERT INTO `audit_action_definitions` "
            "(`code`, `label`, `category`, `resource_type`, `sort_order`, `created_at`) "
            "VALUES (:code, :label, :category, :resource_type, :sort_order, NOW())"
        ), {"code": code, "label": label, "category": category,
            "resource_type": resource_type, "sort_order": sort_order})


def downgrade() -> None:
    # Drop in reverse FK dependency order
    for table in [
        "pool_accounts",
        "pool_model_configs",
        "pools",
        "routing_settings",
        "provider_credentials",
        "routing_configs",
        "model_catalog_category_map",
        "model_catalog",
        "model_categories",
        "model_vendors",
        "admin_audit_logs",
        "audit_action_definitions",
        "admin_users",
        "voucher_redemption_codes",
        "usage_stats",
        "api_call_logs",
        "topup_orders",
        "balance_transactions",
        "user_api_keys",
        "user_sessions",
        "email_verification_codes",
        "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS `{table}`")
