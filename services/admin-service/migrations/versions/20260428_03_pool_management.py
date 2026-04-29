"""Pool management tables: pools, pool_models, pool_accounts."""

from __future__ import annotations

from alembic import op

revision = "20260428_03_pool_management"
down_revision = "20260428_02_config_system_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_pools_slug` (`slug`),
            KEY `idx_pools_enabled` (`is_enabled`),
            CONSTRAINT `fk_pools_created_by` FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_pools_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `pool_models` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `pool_id` BIGINT NOT NULL,
            `model_slug` VARCHAR(120) NOT NULL COMMENT '系统模型标识',
            `upstream_model_id` VARCHAR(200) NOT NULL COMMENT '上游实际模型 ID',
            `input_price_per_million` INT NOT NULL DEFAULT 0 COMMENT '每百万输入 token 价格（分）',
            `output_price_per_million` INT NOT NULL DEFAULT 0 COMMENT '每百万输出 token 价格（分）',
            `cached_input_price_per_million` INT NULL COMMENT '缓存命中输入价格（分）',
            `context_length` INT NULL COMMENT '该平台对此模型的最大上下文长度',
            `is_enabled` TINYINT(1) NOT NULL DEFAULT 1,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_pool_model` (`pool_id`, `model_slug`),
            CONSTRAINT `fk_pool_models_pool` FOREIGN KEY (`pool_id`) REFERENCES `pools` (`id`) ON DELETE CASCADE
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
            `balance` INT NOT NULL DEFAULT 0 COMMENT '余额（分）',
            `status` VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active/disabled/exhausted/error',
            `rpm_limit` INT NULL COMMENT '每分钟请求上限',
            `tpm_limit` INT NULL COMMENT '每分钟 token 上限',
            `weight` INT NOT NULL DEFAULT 1 COMMENT '轮转权重',
            `last_checked_at` DATETIME NULL COMMENT '上次检查时间',
            `remark` VARCHAR(256) NULL,
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            KEY `idx_pool_accounts_pool` (`pool_id`),
            KEY `idx_pool_accounts_status` (`status`),
            CONSTRAINT `fk_pool_accounts_pool` FOREIGN KEY (`pool_id`) REFERENCES `pools` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_pool_accounts_created_by` FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_pool_accounts_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `pool_accounts`")
    op.execute("DROP TABLE IF EXISTS `pool_models`")
    op.execute("DROP TABLE IF EXISTS `pools`")
