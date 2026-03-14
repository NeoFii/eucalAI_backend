SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `news` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `uid` BIGINT NOT NULL COMMENT 'Public news UID',
    `title` VARCHAR(255) NOT NULL COMMENT 'Title',
    `slug` VARCHAR(255) NOT NULL COMMENT 'Slug',
    `summary` VARCHAR(500) NULL COMMENT 'Summary',
    `cover_image` VARCHAR(500) NULL COMMENT 'Cover image URL',
    `content` LONGTEXT NOT NULL COMMENT 'Markdown content',
    `status` SMALLINT NOT NULL DEFAULT 0 COMMENT '0=draft 1=published 2=offline 3=deleted',
    `published_at` DATETIME NULL COMMENT 'Published at',
    `author_id` BIGINT NULL COMMENT 'Author admin id',
    `deleted_at` DATETIME NULL COMMENT 'Soft delete time',
    `deleted_by_admin_id` BIGINT NULL COMMENT 'Soft delete operator admin id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_news_uid` (`uid`),
    UNIQUE KEY `uk_news_slug` (`slug`),
    KEY `idx_news_status_published` (`status`, `published_at`),
    KEY `idx_news_deleted_at` (`deleted_at`),
    KEY `idx_news_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='News';

SET FOREIGN_KEY_CHECKS = 1;
