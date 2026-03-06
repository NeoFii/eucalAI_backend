-- ============================================================
-- 新闻表
-- 用于官网新闻展示，支持 Markdown 内容和双语 (zh/en)
-- ============================================================

DROP TABLE IF EXISTS `news`;

CREATE TABLE `news` (
    -- 内部自增主键
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 对外新闻 ID（雪花 ID）
    `uid` BIGINT NOT NULL COMMENT '对外新闻ID（雪花ID）',

    -- 语言：zh=中文 en=英文
    `language` VARCHAR(10) NOT NULL DEFAULT 'zh' COMMENT '语言: zh=中文 en=英文',

    -- 新闻标题
    `title` VARCHAR(255) NOT NULL COMMENT '新闻标题',

    -- URL 路径标识
    `slug` VARCHAR(255) NOT NULL COMMENT 'URL路径标识',

    -- 摘要
    `summary` VARCHAR(500) NULL COMMENT '摘要',

    -- 封面图 URL
    `cover_image` VARCHAR(500) NULL COMMENT '封面图URL',

    -- Markdown 正文内容
    `content` LONGTEXT NOT NULL COMMENT 'Markdown正文内容',

    -- 新闻状态：0=草稿 1=已发布 2=已下线
    `status` INT NOT NULL DEFAULT 0 COMMENT '状态：0=草稿 1=已发布 2=已下线',

    -- 发布时间
    `published_at` DATETIME NULL COMMENT '发布时间',

    -- 作者 ID（关联 admin_users.id）
    `author_id` BIGINT NULL COMMENT '作者ID（关联admin_users.id）',

    -- 时间戳
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_news_uid` (`uid`),
    UNIQUE KEY `uk_news_language_slug` (`language`, `slug`),
    KEY `idx_news_language` (`language`),
    KEY `idx_news_status` (`status`),
    KEY `idx_news_published_at` (`published_at`),
    KEY `idx_news_language_status_published` (`language`, `status`, `published_at`),
    KEY `idx_news_created_at` (`created_at`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='新闻表';
