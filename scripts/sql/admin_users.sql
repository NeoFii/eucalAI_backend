-- ============================================================
-- 管理员用户表
-- 用于管理员登录认证，与普通用户表分离
-- ============================================================

DROP TABLE IF EXISTS `admin_users`;

CREATE TABLE `admin_users` (
    -- 内部自增主键
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 对外管理员ID（雪花ID）
    `uid` BIGINT NOT NULL COMMENT '对外管理员ID（雪花ID）',

    -- 登录邮箱（唯一）
    `email` VARCHAR(255) NOT NULL COMMENT '登录邮箱',

    -- bcrypt密码哈希
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'bcrypt密码哈希',

    -- 管理员姓名
    `name` VARCHAR(100) NOT NULL COMMENT '管理员姓名',

    -- 管理员状态：0=禁用 1=正常
    `status` INT NOT NULL DEFAULT 1 COMMENT '状态：0=禁用 1=正常',

    -- 角色：super=超级管理员 admin=普通管理员
    `role` VARCHAR(20) NOT NULL DEFAULT 'admin' COMMENT '角色：super=超级管理员 admin=普通管理员',

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
    UNIQUE KEY `uk_admin_users_uid` (`uid`),
    UNIQUE KEY `uk_admin_users_email` (`email`),
    KEY `idx_admin_users_status` (`status`),
    KEY `idx_admin_users_role` (`role`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='管理员用户表';
