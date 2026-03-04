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
