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

CREATE TABLE IF NOT EXISTS `user_active_sessions` (
    `user_id` BIGINT NOT NULL COMMENT 'User id',
    `session_id` BIGINT NOT NULL COMMENT 'Current active session id',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `uk_user_active_sessions_session_id` (`session_id`),
    CONSTRAINT `fk_user_active_sessions_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_user_active_sessions_session_id` FOREIGN KEY (`session_id`) REFERENCES `user_sessions` (`session_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One active session per user';

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

SET FOREIGN_KEY_CHECKS = 1;
