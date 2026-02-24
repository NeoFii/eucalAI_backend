-- ============================================================
-- 邮箱验证码表
-- 用于存储注册和密码重置时发送的验证码
-- ============================================================

DROP TABLE IF EXISTS `email_verification_codes`;

CREATE TABLE `email_verification_codes` (
    -- 内部主键
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',

    -- 邮箱地址
    `email` VARCHAR(255) NOT NULL COMMENT '邮箱地址',

    -- 验证码哈希（bcrypt 加密）
    `code_hash` VARCHAR(255) NOT NULL COMMENT '验证码哈希',

    -- 错误次数
    `error_count` INT NOT NULL DEFAULT 0 COMMENT '错误次数',

    -- 用途：register-注册验证码 reset_password-密码重置 login-免密登录
    `purpose` VARCHAR(20) NOT NULL DEFAULT 'register' COMMENT '用途：register-注册 reset_password-重置密码 login-免密登录',

    -- 过期时间
    `expires_at` DATETIME NOT NULL COMMENT '过期时间',

    -- 锁定截止时间（防刷限制）
    `locked_until` DATETIME NULL COMMENT '锁定截止时间',

    -- 使用时间（已使用则记录时间）
    `used_at` DATETIME NULL COMMENT '使用时间',

    -- 创建时间
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 主键和索引
    PRIMARY KEY (`id`),
    KEY `idx_codes_email` (`email`),
    KEY `idx_codes_email_purpose` (`email`, `purpose`),
    KEY `idx_codes_expires_at` (`expires_at`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='邮箱验证码表';
