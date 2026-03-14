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

CREATE TABLE IF NOT EXISTS `invitation_codes` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `code` VARCHAR(64) NOT NULL COMMENT 'Invitation code',
    `status` SMALLINT NOT NULL DEFAULT 0 COMMENT '0=unused 1=used 2=disabled',
    `created_by` BIGINT NULL COMMENT 'Creator admin id',
    `used_by` BIGINT NULL COMMENT 'Used-by user UID',
    `used_at` DATETIME NULL COMMENT 'Used at',
    `expires_at` DATETIME NULL COMMENT 'Expires at',
    `remark` TEXT NULL COMMENT 'Remark',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_invitation_codes_code` (`code`),
    KEY `idx_invitation_codes_status` (`status`),
    KEY `idx_invitation_codes_created_by` (`created_by`),
    KEY `idx_invitation_codes_used_by` (`used_by`),
    KEY `idx_invitation_codes_created_at` (`created_at`),
    CONSTRAINT `fk_invitation_codes_created_by` FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Invitation codes';

SET FOREIGN_KEY_CHECKS = 1;
