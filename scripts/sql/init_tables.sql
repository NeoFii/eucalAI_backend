-- ============================================================
-- Eucal AI 后端数据库建表语句
-- 数据库: MySQL 8.0+
-- 字符集: utf8mb4
-- ============================================================


-- ============================================================
-- 用户表
-- ============================================================
DROP TABLE IF EXISTS `users`;

CREATE TABLE `users` (
    -- 内部自增主键
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 对外用户ID（雪花ID）
    `uid` BIGINT NOT NULL COMMENT '对外用户ID（雪花ID）',

    -- 登录邮箱
    `email` VARCHAR(255) NOT NULL COMMENT '登录邮箱',

    -- 密码哈希（bcrypt）
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'bcrypt密码哈希',

    -- 用户状态：0=禁用 1=正常 2=待验证
    `status` SMALLINT NOT NULL DEFAULT 1 COMMENT '状态：0=禁用 1=正常 2=待验证',

    -- 邮箱验证时间
    `email_verified_at` DATETIME NULL COMMENT '邮箱验证时间',

    -- 最近登录时间
    `last_login_at` DATETIME NULL COMMENT '最近登录时间',

    -- 最近登录IP
    `last_login_ip` VARCHAR(45) NULL COMMENT '最近登录IP',

    -- 登录失败次数
    `login_fail_count` INT NOT NULL DEFAULT 0 COMMENT '登录失败次数',

    -- 登录锁定截止时间
    `login_locked_until` DATETIME NULL COMMENT '登录锁定截止时间',

    -- 时间戳
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_users_uid` (`uid`),
    UNIQUE KEY `uk_users_email` (`email`),
    KEY `idx_users_status` (`status`),
    KEY `idx_users_created_at` (`created_at`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='用户表';

-- ============================================================
-- 用户会话表
-- ============================================================
DROP TABLE IF EXISTS `user_sessions`;

CREATE TABLE `user_sessions` (
    -- 内部自增主键
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 会话ID（雪花ID）
    `session_id` BIGINT NOT NULL COMMENT '会话ID（雪花ID）',

    -- 关联用户ID
    `user_id` BIGINT NOT NULL COMMENT '关联用户ID',

    -- refresh_token 标识和哈希
    `token_jti` VARCHAR(64) NOT NULL COMMENT 'refresh_token的jti标识（SHA256哈希，用于快速查找）',
    `refresh_token_hash` VARCHAR(255) NOT NULL COMMENT 'refresh_token的bcrypt哈希（用于验证真实性)',

    -- 客户端信息
    `user_agent` VARCHAR(512) NULL COMMENT '客户端User-Agent',
    `ip_address` VARCHAR(45) NULL COMMENT '客户端IP地址',

    -- 会话有效期
    `expires_at` DATETIME NOT NULL COMMENT '过期时间',

    -- 注销时间
    `revoked_at` DATETIME NULL COMMENT '注销时间',

    -- 创建时间
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 更新时间
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_sessions_session_id` (`session_id`),
    UNIQUE KEY `uk_sessions_token_jti` (`token_jti`),
    KEY `idx_sessions_user_id` (`user_id`),
    KEY `idx_sessions_token_jti` (`token_jti`),
    KEY `idx_sessions_expires_at` (`expires_at`),
    KEY `idx_sessions_revoked_at` (`revoked_at`),

    -- 外键约束
    CONSTRAINT `fk_sessions_user_id`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='用户会话表';

-- ============================================================
-- 邮箱验证码表
-- 用于存储注册、密码重置和免密登录时发送的验证码
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

-- ============================================================
-- 邀请码表
-- 用于邀请注册机制，控制用户注册权限
-- ============================================================
DROP TABLE IF EXISTS `invitation_codes`;

CREATE TABLE `invitation_codes` (
    -- 内部自增主键
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 邀请码字符串（对外使用，唯一）
    `code` VARCHAR(64) NOT NULL COMMENT '邀请码字符串（22位高熵随机字符串）',

    -- 邀请码状态：0=未使用, 1=已使用, 2=已弃用
    `status` INT NOT NULL DEFAULT 0 COMMENT '状态：0=未使用, 1=已使用, 2=已弃用',

    -- 创建者 uid（预留，管理员创建时填写）
    `created_by` BIGINT NULL COMMENT '创建者 uid（管理员）',

    -- 使用者 uid（注册成功后填写）
    `used_by` BIGINT NULL COMMENT '使用者 uid（注册成功后填写）',

    -- 使用时间
    `used_at` DATETIME NULL COMMENT '使用时间',

    -- 过期时间（NULL 表示永不过期）
    `expires_at` DATETIME NULL COMMENT '过期时间（NULL表示永不过期）',

    -- 管理备注
    `remark` VARCHAR(255) NULL COMMENT '管理备注',

    -- 时间戳
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_invitation_codes_code` (`code`),
    KEY `idx_invitation_codes_status` (`status`),
    KEY `idx_invitation_codes_created_by` (`created_by`),
    KEY `idx_invitation_codes_used_by` (`used_by`),
    KEY `idx_invitation_codes_created_at` (`created_at`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='邀请码表';

-- ============================================================
-- 索引优化说明
-- ============================================================
-- users 表:
--   - uid: 用于快速查找用户（雪花ID查询）
--   - email: 用于登录验证
--   - status: 用于筛选正常用户
--   - created_at: 用于排序和统计
--
-- user_sessions 表:
--   - session_id: 用于快速定位会话
--   - user_id: 用于查询用户的所有会话
--   - token_jti: 用于快速查找会话（SHA256索引）
--   - refresh_token_hash: 用于验证refresh_token真实性（bcrypt）
--   - expires_at: 用于清理过期会话
--   - revoked_at: 用于查询有效会话
--
-- invitation_codes 表:
--   - code: 用于验证邀请码（唯一索引）
--   - status: 用于筛选未使用的邀请码
--   - created_by: 用于查询管理员创建的邀请码
--   - used_by: 用于查询用户使用的邀请码
--   - created_at: 用于排序和统计
