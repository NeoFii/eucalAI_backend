"""Admin service consolidated baseline — all tables + seed catalog data."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260501_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `admin_users` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `uid` VARCHAR(20) NOT NULL COMMENT 'Public admin UID (NanoID)',
            `email` VARCHAR(255) NOT NULL COMMENT 'Login email',
            `password_hash` VARCHAR(255) NOT NULL COMMENT 'Password hash',
            `name` VARCHAR(100) NOT NULL COMMENT 'Admin display name',
            `status` SMALLINT NOT NULL DEFAULT 1 COMMENT '0=disabled 1=active',
            `role` VARCHAR(20) NOT NULL DEFAULT 'admin' COMMENT 'admin/super_admin',
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
                ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Admin users'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `admin_audit_logs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `actor_admin_id` BIGINT NOT NULL COMMENT 'Actor admin id',
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
            CONSTRAINT `fk_audit_logs_actor`
                FOREIGN KEY (`actor_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE RESTRICT,
            CONSTRAINT `fk_audit_logs_target`
                FOREIGN KEY (`target_admin_id`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL
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
        CREATE TABLE IF NOT EXISTS `supported_models` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `slug` VARCHAR(120) NOT NULL COMMENT 'Model slug',
            `routing_slug` VARCHAR(200) NULL COMMENT '路由用 slug，对应 pool_models.model_slug',
            `name` VARCHAR(160) NOT NULL COMMENT 'Model display name',
            `vendor_id` BIGINT NOT NULL COMMENT 'Model vendor id',
            `summary` VARCHAR(255) NULL COMMENT 'Model card summary',
            `description` TEXT NULL COMMENT 'Model detail description',
            `price_input_per_m_fen` BIGINT NULL COMMENT 'Input price per million tokens (micro-yuan)',
            `price_output_per_m_fen` BIGINT NULL COMMENT 'Output price per million tokens (micro-yuan)',
            `price_cached_input_per_m_fen` BIGINT NULL COMMENT 'Cached input price per million tokens (micro-yuan)',
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
            UNIQUE KEY `uk_supported_models_slug` (`slug`),
            UNIQUE KEY `uk_supported_models_routing_slug` (`routing_slug`),
            KEY `idx_supported_models_vendor_id` (`vendor_id`),
            CONSTRAINT `fk_supported_models_vendor_id`
                FOREIGN KEY (`vendor_id`) REFERENCES `model_vendors` (`id`)
                ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Supported models'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `supported_model_category_map` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `model_id` BIGINT NOT NULL COMMENT 'Supported model id',
            `category_id` BIGINT NOT NULL COMMENT 'Model category id',
            `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Model-local category order',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_supported_model_category` (`model_id`, `category_id`),
            KEY `idx_model_category_map_model_id` (`model_id`),
            KEY `idx_model_category_map_category_id` (`category_id`),
            CONSTRAINT `fk_model_category_map_model_id`
                FOREIGN KEY (`model_id`) REFERENCES `supported_models` (`id`)
                ON DELETE CASCADE,
            CONSTRAINT `fk_model_category_map_category_id`
                FOREIGN KEY (`category_id`) REFERENCES `model_categories` (`id`)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Supported model to category mapping'
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
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_pools_slug` (`slug`),
            KEY `idx_pools_enabled` (`is_enabled`),
            CONSTRAINT `fk_pools_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_pools_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
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
            `input_price_per_million` BIGINT NOT NULL DEFAULT 0 COMMENT '每百万输入 token 价格 (micro-yuan)',
            `output_price_per_million` BIGINT NOT NULL DEFAULT 0 COMMENT '每百万输出 token 价格 (micro-yuan)',
            `cached_input_price_per_million` BIGINT NULL COMMENT '缓存命中输入价格 (micro-yuan)',
            `context_length` INT NULL COMMENT '该平台对此模型的最大上下文长度',
            `is_enabled` TINYINT(1) NOT NULL DEFAULT 1,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_pool_model` (`pool_id`, `model_slug`),
            CONSTRAINT `fk_pool_models_pool`
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
            `status` VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active/disabled/exhausted/error',
            `rpm_limit` INT NULL COMMENT '每分钟请求上限',
            `tpm_limit` INT NULL COMMENT '每分钟 token 上限',
            `weight` INT NOT NULL DEFAULT 1 COMMENT '轮转权重',
            `last_checked_at` DATETIME NULL COMMENT '上次检查时间',
            `last_health_check_error` VARCHAR(512) NULL COMMENT '上次健康检查错误信息',
            `remark` VARCHAR(256) NULL,
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            KEY `idx_pool_accounts_pool` (`pool_id`),
            KEY `idx_pool_accounts_status` (`status`),
            CONSTRAINT `fk_pool_accounts_pool`
                FOREIGN KEY (`pool_id`) REFERENCES `pools` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_pool_accounts_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
            CONSTRAINT `fk_pool_accounts_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    _seed_catalog()
    _seed_routing_settings()


def _seed_routing_settings() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            INSERT IGNORE INTO `routing_settings`
                (`key`, `value`, `value_type`, `group_name`, `label`, `description`, `sort_order`)
            VALUES
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
                ('tier_5_model',   'gpt-oss-120b',    'string', 'tier_model_map', 'Tier 5 模型', '最低难度', 5)
            """
        )
    )


def _seed_catalog() -> None:
    _exec = lambda sql: op.execute(text(sql))

    for slug, name, logo_url, sort_order in [
        ("deepseek", "DeepSeek", "/icons/providers/deepseek.png", 10),
        ("openai", "OpenAI", "/icons/providers/openai.png", 20),
        ("anthropic", "Anthropic", "/icons/providers/anthropic.png", 30),
        ("google", "Google", "/icons/providers/google.png", 40),
    ]:
        _exec(
            f"INSERT INTO model_vendors (slug, name, logo_url, is_active, sort_order) "
            f"SELECT '{slug}', '{name}', '{logo_url}', 1, {sort_order} "
            f"WHERE NOT EXISTS (SELECT 1 FROM model_vendors WHERE slug = '{slug}')"
        )

    for key, name, sort_order in [
        ("reasoning", "Reasoning", 1),
        ("coding", "Coding", 2),
        ("tool_use", "Tool use", 3),
        ("instruction_following", "Instruction following", 4),
    ]:
        _exec(
            f"INSERT INTO model_categories (`key`, name, sort_order, is_active) "
            f"SELECT '{key}', '{name}', {sort_order}, 1 "
            f"WHERE NOT EXISTS (SELECT 1 FROM model_categories WHERE `key` = '{key}')"
        )

    models = [
        (
            "deepseek-v3-2", "DeepSeek-V3.2", "deepseek",
            "通用旗舰模型，兼顾聊天、代码与复杂任务执行。",
            "DeepSeek-V3.2 是一款面向通用生产场景的旗舰模型，在代码生成、长上下文问答和复杂任务执行之间保持均衡表现。",
            '["chat","coding","reasoning"]', 128000, 8192, 0, 10,
            ["coding", "instruction_following"],
        ),
        (
            "deepseek-r1", "DeepSeek-R1", "deepseek",
            "强化推理模型，适合数学、代码与多步骤规划。",
            "DeepSeek-R1 聚焦推理与规划任务，适合数学证明、代码推导和需要清晰中间步骤的复杂分析。",
            '["chat","reasoning","coding"]', 128000, 8192, 1, 20,
            ["reasoning", "coding"],
        ),
        (
            "gpt-4o", "GPT-4o", "openai",
            "多模态通用模型，适合实时交互与工具调用。",
            "GPT-4o 提供文本、图像等多模态能力，适合需要实时响应、工具协同和稳定通用表现的应用。",
            '["chat","vision","tool_calling"]', 128000, 16384, 0, 30,
            ["tool_use", "instruction_following"],
        ),
        (
            "claude-sonnet-4", "Claude Sonnet 4", "anthropic",
            "偏向代码与代理工作流的均衡模型。",
            "Claude Sonnet 4 在代码理解、代理式工作流和长文档处理上表现稳健，适合工程协作与复杂业务自动化。",
            '["chat","coding","tool_calling"]', 200000, 8192, 0, 40,
            ["coding", "tool_use", "instruction_following"],
        ),
    ]
    for slug, name, vendor_slug, summary, description, tags, context, output, reasoning, order, categories in models:
        desc_escaped = description.replace("'", "\\'")
        summ_escaped = summary.replace("'", "\\'")
        _exec(
            f"INSERT INTO supported_models "
            f"(slug, name, vendor_id, summary, description, capability_tags, "
            f"context_window, max_output_tokens, is_reasoning_model, is_active, sort_order) "
            f"SELECT '{slug}', '{name}', model_vendors.id, '{summ_escaped}', '{desc_escaped}', "
            f"'{tags}', {context}, {output}, {reasoning}, 1, {order} "
            f"FROM model_vendors WHERE model_vendors.slug = '{vendor_slug}' "
            f"AND NOT EXISTS (SELECT 1 FROM supported_models WHERE slug = '{slug}')"
        )
        for index, category in enumerate(categories, start=1):
            _exec(
                f"INSERT INTO supported_model_category_map (model_id, category_id, sort_order) "
                f"SELECT supported_models.id, model_categories.id, {index} "
                f"FROM supported_models, model_categories "
                f"WHERE supported_models.slug = '{slug}' "
                f"AND model_categories.`key` = '{category}' "
                f"AND NOT EXISTS ("
                f"SELECT 1 FROM supported_model_category_map "
                f"WHERE model_id = supported_models.id AND category_id = model_categories.id)"
            )


def downgrade() -> None:
    for table in [
        "pool_accounts", "pool_models", "pools",
        "routing_settings",
        "provider_credentials", "routing_configs",
        "supported_model_category_map", "supported_models",
        "model_categories", "model_vendors",
        "admin_audit_logs", "admin_users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS `{table}`")
