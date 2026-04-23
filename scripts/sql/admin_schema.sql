SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `admin_users` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `uid` BIGINT NOT NULL COMMENT 'Public admin UID',
    `email` VARCHAR(255) NOT NULL COMMENT 'Login email',
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'Password hash',
    `name` VARCHAR(100) NOT NULL COMMENT 'Admin display name',
    `status` SMALLINT NOT NULL DEFAULT 1 COMMENT '0=disabled 1=active',
    `role` VARCHAR(20) NOT NULL DEFAULT 'admin' COMMENT 'admin/super_admin',
    `created_by_admin_id` BIGINT NULL COMMENT 'Creator admin id',
    `updated_by_admin_id` BIGINT NULL COMMENT 'Last updater admin id',
    `password_changed_at` DATETIME NULL COMMENT 'Last password change time',
    `password_changed_by_admin_id` BIGINT NULL COMMENT 'Last password changer admin id',
    `last_login_at` DATETIME NULL COMMENT 'Last login time',
    `last_login_ip` VARCHAR(45) NULL COMMENT 'Last login IP',
    `login_fail_count` INT NOT NULL DEFAULT 0 COMMENT 'Failed login count',
    `login_locked_until` DATETIME NULL COMMENT 'Login lock expiry',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_users_uid` (`uid`),
    UNIQUE KEY `uk_admin_users_email` (`email`),
    KEY `idx_admin_users_status` (`status`),
    KEY `idx_admin_users_role` (`role`),
    KEY `idx_admin_users_created_by` (`created_by_admin_id`),
    KEY `idx_admin_users_updated_by` (`updated_by_admin_id`),
    CONSTRAINT `fk_admin_users_created_by` FOREIGN KEY (`created_by_admin_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_admin_users_updated_by` FOREIGN KEY (`updated_by_admin_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_admin_users_password_changed_by` FOREIGN KEY (`password_changed_by_admin_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Admin users';

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
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    PRIMARY KEY (`id`),
    KEY `idx_admin_audit_actor_time` (`actor_admin_id`, `created_at`),
    KEY `idx_admin_audit_target_time` (`target_admin_id`, `created_at`),
    KEY `idx_admin_audit_resource` (`resource_type`, `resource_id`, `created_at`),
    KEY `idx_admin_audit_action_time` (`action`, `created_at`),
    CONSTRAINT `fk_admin_audit_actor` FOREIGN KEY (`actor_admin_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_admin_audit_target` FOREIGN KEY (`target_admin_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Admin audit logs';

CREATE TABLE IF NOT EXISTS `model_vendors` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `slug` VARCHAR(80) NOT NULL COMMENT 'Vendor slug',
    `name` VARCHAR(120) NOT NULL COMMENT 'Vendor display name',
    `logo_url` VARCHAR(512) NULL COMMENT 'Vendor logo URL',
    `is_active` BOOL NOT NULL DEFAULT 1 COMMENT 'Whether vendor is active',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_vendors_slug` (`slug`),
    KEY `idx_model_vendors_sort_order` (`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model vendors';

CREATE TABLE IF NOT EXISTS `model_categories` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `key` VARCHAR(80) NOT NULL COMMENT 'Category key',
    `name` VARCHAR(120) NOT NULL COMMENT 'Category display name',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
    `is_active` BOOL NOT NULL DEFAULT 1 COMMENT 'Whether category is active',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_categories_key` (`key`),
    KEY `idx_model_categories_sort_order` (`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model categories';

CREATE TABLE IF NOT EXISTS `supported_models` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `slug` VARCHAR(120) NOT NULL COMMENT 'Model slug',
    `name` VARCHAR(160) NOT NULL COMMENT 'Model display name',
    `vendor_id` BIGINT NOT NULL COMMENT 'Model vendor id',
    `summary` VARCHAR(255) NULL COMMENT 'Model card summary',
    `description` TEXT NULL COMMENT 'Model detail description',
    `price_input_per_m_fen` INT NULL COMMENT 'Input price per million tokens in fen',
    `price_output_per_m_fen` INT NULL COMMENT 'Output price per million tokens in fen',
    `capability_tags` JSON NOT NULL COMMENT 'Capability tag list',
    `context_window` INT NULL COMMENT 'Context window tokens',
    `max_output_tokens` INT NULL COMMENT 'Max output tokens',
    `is_reasoning_model` BOOL NOT NULL DEFAULT 0 COMMENT 'Whether this is a reasoning model',
    `is_active` BOOL NOT NULL DEFAULT 1 COMMENT 'Whether model is active',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Display sort order',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_supported_models_slug` (`slug`),
    KEY `idx_supported_models_vendor_id` (`vendor_id`),
    KEY `idx_supported_models_sort_order` (`sort_order`),
    CONSTRAINT `fk_supported_models_vendor` FOREIGN KEY (`vendor_id`) REFERENCES `model_vendors` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Supported models';

CREATE TABLE IF NOT EXISTS `supported_model_category_map` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `model_id` BIGINT NOT NULL COMMENT 'Supported model id',
    `category_id` BIGINT NOT NULL COMMENT 'Model category id',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Model-local category order',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_supported_model_category` (`model_id`, `category_id`),
    KEY `idx_supported_model_category_model_id` (`model_id`),
    KEY `idx_supported_model_category_category_id` (`category_id`),
    CONSTRAINT `fk_supported_model_category_model` FOREIGN KEY (`model_id`) REFERENCES `supported_models` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_supported_model_category_category` FOREIGN KEY (`category_id`) REFERENCES `model_categories` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Supported model category map';

CREATE TABLE IF NOT EXISTS `provider_credentials` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `slug` VARCHAR(64) NOT NULL COMMENT 'Credential reference slug',
    `provider_slug` VARCHAR(64) NOT NULL COMMENT 'Provider identifier',
    `api_key_enc` JSON NOT NULL COMMENT 'AES-256-GCM encrypted API key',
    `mask` VARCHAR(32) NOT NULL COMMENT 'Masked API key for display',
    `is_active` BOOL NOT NULL DEFAULT 1 COMMENT 'Whether credential is active',
    `remark` VARCHAR(256) NULL COMMENT 'Remark',
    `created_by` BIGINT NOT NULL COMMENT 'Creator admin id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_provider_credentials_slug` (`slug`),
    CONSTRAINT `fk_provider_credentials_created_by` FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Provider credentials';

CREATE TABLE IF NOT EXISTS `routing_configs` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `version` INT NOT NULL COMMENT 'Config version number',
    `status` VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT 'draft/active/superseded',
    `config_data` JSON NOT NULL COMMENT 'Full routing policy JSON',
    `description` VARCHAR(512) NULL COMMENT 'Version description',
    `published_at` DATETIME NULL COMMENT 'Published at',
    `published_by` BIGINT NULL COMMENT 'Publisher admin id',
    `created_by` BIGINT NOT NULL COMMENT 'Creator admin id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_routing_configs_version` (`version`),
    KEY `idx_routing_configs_status` (`status`),
    CONSTRAINT `fk_routing_configs_published_by` FOREIGN KEY (`published_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_routing_configs_created_by` FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Routing configs';

SET FOREIGN_KEY_CHECKS = 1;
