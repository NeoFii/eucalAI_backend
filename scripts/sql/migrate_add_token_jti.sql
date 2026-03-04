-- ============================================================
-- 迁移脚本：添加 token_jti 字段到 user_sessions 表
-- 用途：支持 refresh_token 的双重验证机制
-- ============================================================

-- 添加 token_jti 字段
ALTER TABLE `user_sessions`
ADD COLUMN `token_jti` VARCHAR(64) NULL COMMENT 'refresh_token的jti标识（SHA256哈希，用于快速查找）' AFTER `user_id`;

-- 为现有数据生成临时 jti（基于现有 session_id 的哈希）
-- 注意：这只是一个临时值，用户需要重新登录才能使用新的 token 系统
UPDATE `user_sessions`
SET `token_jti` = SHA2(CONCAT(`session_id`, '-', `created_at`), 256)
WHERE `token_jti` IS NULL;

-- 修改字段为 NOT NULL
ALTER TABLE `user_sessions`
MODIFY COLUMN `token_jti` VARCHAR(64) NOT NULL COMMENT 'refresh_token的jti标识（SHA256哈希，用于快速查找）';

-- 添加唯一索引
ALTER TABLE `user_sessions`
ADD UNIQUE KEY `uk_sessions_token_jti` (`token_jti`);

-- 添加普通索引用于查询
ALTER TABLE `user_sessions`
ADD KEY `idx_sessions_token_jti` (`token_jti`);

-- 删除旧的索引（如果存在）
-- 注意：MySQL 8.0+ 支持 DROP INDEX IF EXISTS，旧版本请手动检查
-- 如果 idx_sessions_refresh_token 存在，执行以下语句：
-- ALTER TABLE `user_sessions` DROP INDEX `idx_sessions_refresh_token`;

-- 修改 refresh_token_hash 字段注释
ALTER TABLE `user_sessions`
MODIFY COLUMN `refresh_token_hash` VARCHAR(255) NOT NULL COMMENT 'refresh_token的bcrypt哈希（用于验证真实性)';

-- ============================================================
-- 重要说明：
-- 1. 运行此迁移后，现有会话的 token_jti 是临时生成的
-- 2. 用户需要重新登录才能正常使用 refresh_token 功能
-- 3. 建议在低峰期运行此迁移
-- ============================================================
