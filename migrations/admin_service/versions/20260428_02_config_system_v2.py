"""Config system v2: routing_settings, api_channels, channel_model_abilities, model_paths_configs."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260428_02_config_system_v2"
down_revision = "20260423_01_admin_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `routing_settings` (
            `key` VARCHAR(64) NOT NULL COMMENT '配置键',
            `value` TEXT NOT NULL COMMENT '配置值',
            `value_type` VARCHAR(16) NOT NULL DEFAULT 'string' COMMENT 'string/float/int',
            `group_name` VARCHAR(32) NOT NULL COMMENT 'general/weights/score_bands/tier_model_map',
            `label` VARCHAR(128) NOT NULL COMMENT '管理端显示名',
            `description` VARCHAR(512) NULL,
            `sort_order` INT NOT NULL DEFAULT 0,
            `updated_by` BIGINT NULL,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`key`),
            KEY `idx_routing_settings_group` (`group_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='路由策略 key-value 配置';
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `api_channels` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `slug` VARCHAR(64) NOT NULL COMMENT '引用标识',
            `name` VARCHAR(128) NOT NULL COMMENT '显示名称',
            `provider_slug` VARCHAR(64) NOT NULL COMMENT '供应商标识',
            `api_key_enc` JSON NOT NULL COMMENT 'AES-256-GCM encrypted {ciphertext,iv,tag}',
            `mask` VARCHAR(32) NOT NULL COMMENT '脱敏显示 e.g. sk-1****89ab',
            `api_base` VARCHAR(512) NOT NULL COMMENT 'API base URL',
            `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
            `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级，越大越优先',
            `weight` INT NOT NULL DEFAULT 1 COMMENT '轮选权重',
            `remark` VARCHAR(256) NULL,
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_api_channels_slug` (`slug`),
            CONSTRAINT `fk_api_channels_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_api_channels_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='API 渠道号池';
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `channel_model_abilities` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `channel_id` BIGINT NOT NULL,
            `model_slug` VARCHAR(120) NOT NULL COMMENT '逻辑模型名',
            `upstream_model` VARCHAR(200) NOT NULL COMMENT '上游实际模型名',
            `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
            `priority` INT NOT NULL DEFAULT 0 COMMENT '同模型多渠道时的优先级',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_channel_model` (`channel_id`, `model_slug`),
            KEY `idx_model_slug` (`model_slug`),
            CONSTRAINT `fk_cma_channel`
                FOREIGN KEY (`channel_id`) REFERENCES `api_channels` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='渠道-模型能力映射';
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `model_paths_configs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `version` INT NOT NULL,
            `status` VARCHAR(16) NOT NULL DEFAULT 'draft'
                COMMENT 'draft / active / superseded',
            `config_data` JSON NOT NULL
                COMMENT 'ML model paths JSON (qwen_backbone, routers, device, etc.)',
            `description` VARCHAR(512) NULL,
            `published_at` DATETIME NULL,
            `published_by` BIGINT NULL,
            `created_by` BIGINT NOT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_model_paths_version` (`version`),
            KEY `idx_model_paths_status` (`status`),
            CONSTRAINT `fk_mpc_published_by`
                FOREIGN KEY (`published_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_mpc_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='版本化 ML 模型路径配置';
        """
    )

    # Seed routing_settings
    conn = op.get_bind()
    conn.execute(
        text(
            """
            INSERT IGNORE INTO `routing_settings` (`key`, `value`, `value_type`, `group_name`, `label`, `description`, `sort_order`) VALUES
            ('router_alias',   'auto', 'string', 'general',       '路由别名',     '触发智能路由的模型名', 0),
            ('weight_纠错',     '1.0',  'float',  'weights',       '纠错权重',     NULL, 1),
            ('weight_工具调用',  '1.0',  'float',  'weights',       '工具调用权重',  NULL, 2),
            ('weight_通用任务',  '1.0',  'float',  'weights',       '通用任务权重',  NULL, 3),
            ('weight_任务拆解',  '1.0',  'float',  'weights',       '任务拆解权重',  NULL, 4),
            ('weight_编程',     '1.0',  'float',  'weights',       '编程权重',     NULL, 5),
            ('score_bands',    '0-3:5,3-5:4,5-7:3,7-9:2,9-10:1', 'string', 'score_bands', '分数段映射', '格式: start-end:tier,...', 0),
            ('tier_1_model',   'gpt-5-4',        'string', 'tier_model_map', 'Tier 1 模型', '最高难度', 1),
            ('tier_2_model',   'minimax-m2-7',    'string', 'tier_model_map', 'Tier 2 模型', NULL, 2),
            ('tier_3_model',   'glm-4-5-air',     'string', 'tier_model_map', 'Tier 3 模型', NULL, 3),
            ('tier_4_model',   'step-3-5-flash',  'string', 'tier_model_map', 'Tier 4 模型', NULL, 4),
            ('tier_5_model',   'gpt-oss-120b',    'string', 'tier_model_map', 'Tier 5 模型', '最低难度', 5);
            """
        )
    )


def downgrade() -> None:
    for table in ("channel_model_abilities", "api_channels", "model_paths_configs", "routing_settings"):
        op.execute(f"DROP TABLE IF EXISTS `{table}`")
