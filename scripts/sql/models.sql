-- ============================================================
-- 模型页面数据库建表语句
-- 数据库: MySQL 8.0+（需要窗口函数支持）
-- 字符集: utf8mb4
-- 说明:
--   model_vendors  → 研发商（创造模型的公司：Anthropic / OpenAI / DeepSeek）
--   providers      → 服务提供商（提供 API 访问的公司：OpenRouter / Azure / 直连）
--   两者严格分离，不可混用
-- ============================================================


-- ============================================================
-- 删除视图（先删视图再删表，避免依赖报错）
-- ============================================================
DROP VIEW IF EXISTS `provider_metrics_ranked`;


-- ============================================================
-- 删除表（按依赖逆序）
-- ============================================================
DROP TABLE IF EXISTS `provider_performance_metrics`;
DROP TABLE IF EXISTS `model_provider_offerings`;
DROP TABLE IF EXISTS `model_category_map`;
DROP TABLE IF EXISTS `models`;
DROP TABLE IF EXISTS `model_vendors`;
DROP TABLE IF EXISTS `model_categories`;
DROP TABLE IF EXISTS `providers`;


-- ============================================================
-- 表1：模型能力分类
-- 用于前端 Tab 筛选：逻辑推理与规划 / 编程 / 工具调用 / 复杂指令遵循
-- ============================================================
CREATE TABLE `model_categories` (

    -- 内部自增主键
    `id`         BIGINT      NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 分类标识键，供 API 参数使用
    `key`        VARCHAR(50) NOT NULL COMMENT '分类键，如 reasoning / coding / tool_use / instruction_following',

    -- 前端显示名称
    `name`       VARCHAR(100) NOT NULL COMMENT '显示名，如 逻辑推理与规划',

    -- 排序权重，越小越靠前
    `sort_order` SMALLINT    NOT NULL DEFAULT 0 COMMENT '排序权重',

    -- 是否启用
    `is_active`  TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '是否启用：1=启用 0=禁用',

    -- 时间戳
    `created_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_categories_key` (`key`),
    KEY `idx_model_categories_sort` (`sort_order`, `is_active`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='模型能力分类';

-- 初始化四大分类数据
INSERT INTO `model_categories` (`key`, `name`, `sort_order`) VALUES
    ('reasoning',             '逻辑推理与规划', 1),
    ('coding',                '编程',          2),
    ('tool_use',              '工具调用',       3),
    ('instruction_following', '复杂指令遵循',   4);


-- ============================================================
-- 表2：模型研发商
-- 创造模型的公司，如 Anthropic / OpenAI / DeepSeek / Google
-- 注意：研发商 ≠ 服务提供商（providers 表）
-- ============================================================
CREATE TABLE `model_vendors` (

    -- 内部自增主键
    `id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 研发商唯一标识，供 API 参数使用
    `slug`       VARCHAR(100) NOT NULL COMMENT '研发商标识，如 openai / anthropic / deepseek',

    -- 研发商显示名称
    `name`       VARCHAR(200) NOT NULL COMMENT '显示名称',

    -- Logo 图片地址
    `logo_url`   TEXT         COMMENT 'Logo 图片地址',

    -- 是否启用
    `is_active`  TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用：1=启用 0=禁用',

    -- 时间戳
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_vendors_slug` (`slug`),
    KEY `idx_model_vendors_is_active` (`is_active`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='模型研发商（创造模型的公司）';


-- ============================================================
-- 表3：AI 模型本体
-- 一条记录代表一个模型（如 Claude 3.7 Sonnet、GPT-4o）
-- capability_tags 使用 JSON 数组存储能力标签，查询用 JSON_CONTAINS()
-- ============================================================
CREATE TABLE `models` (

    -- 内部自增主键
    `id`                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 关联研发商
    `vendor_id`          BIGINT       NOT NULL COMMENT '关联研发商 ID（model_vendors.id）',

    -- 对外模型标识，供 API 使用
    `slug`               VARCHAR(100) NOT NULL COMMENT '对外模型标识，如 gpt-4o / claude-3-7-sonnet',

    -- 前端显示名称
    `name`               VARCHAR(200) NOT NULL COMMENT '显示名称',

    -- 模型描述
    `description`        TEXT         COMMENT '模型描述',

    -- 能力标签 JSON 数组，如 ["chat","reasoning","vision","tool_calling"]
    -- 查询示例：JSON_CONTAINS(capability_tags, '"reasoning"', '$')
    `capability_tags`    JSON         NOT NULL COMMENT '能力标签数组，如 ["chat","reasoning","vision"]',

    -- 上下文窗口大小（tokens）
    `context_window`     INT          COMMENT '上下文窗口（tokens）',

    -- 最大输出 tokens
    `max_output_tokens`  INT          COMMENT '最大输出 tokens',

    -- 知识截止日期
    `knowledge_cutoff`   DATE         COMMENT '知识截止日期',

    -- 冗余字段：是否为推理模型，方便快速过滤，无需解析 JSON
    `is_reasoning_model` TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否为推理模型（冗余字段，方便快速过滤）',

    -- 全局排序权重（跨所有分类）
    `sort_order`         INT          NOT NULL DEFAULT 0 COMMENT '全局排序权重',

    -- 是否启用
    `is_active`          TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用：1=启用 0=禁用',

    -- 时间戳
    `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_models_slug` (`slug`),
    KEY `idx_models_vendor_id` (`vendor_id`),
    KEY `idx_models_is_active` (`is_active`),
    KEY `idx_models_sort_order` (`sort_order`),

    -- 外键：关联研发商
    CONSTRAINT `fk_models_vendor_id`
        FOREIGN KEY (`vendor_id`) REFERENCES `model_vendors` (`id`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='AI 模型本体';


-- ============================================================
-- 表4：模型 ↔ 分类关联（多对多）
-- 一个模型可属于多个分类（如 GPT-4o 同时属于 reasoning 和 coding）
-- sort_order 为该模型在该分类下的位置权重，与 models.sort_order 共同决定排序
-- ============================================================
CREATE TABLE `model_category_map` (

    -- 关联模型 ID
    `model_id`    BIGINT   NOT NULL COMMENT '关联模型 ID（models.id）',

    -- 关联分类 ID
    `category_id` BIGINT   NOT NULL COMMENT '关联分类 ID（model_categories.id）',

    -- 模型在该分类下的排序权重（越小越靠前）
    -- 第1排序优先级，高于 models.sort_order（全局权重）
    `sort_order`  INT      NOT NULL DEFAULT 0 COMMENT '模型在该分类下的排序权重',

    -- 创建时间（记录关联关系何时建立）
    `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 主键和约束
    PRIMARY KEY (`model_id`, `category_id`),
    KEY `idx_mcm_category_sort` (`category_id`, `sort_order`),

    -- 外键：级联删除
    CONSTRAINT `fk_mcm_model_id`
        FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_mcm_category_id`
        FOREIGN KEY (`category_id`) REFERENCES `model_categories` (`id`) ON DELETE CASCADE

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='模型-分类多对多关联';


-- ============================================================
-- 表5：API 服务提供商
-- 提供模型 API 访问的公司，如 OpenRouter / Azure / 直连（官方 API）
-- 注意：服务提供商 ≠ 研发商（model_vendors 表）
-- ============================================================
CREATE TABLE `providers` (

    -- 内部自增主键
    `id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 提供商唯一标识，供 API 使用
    `slug`       VARCHAR(100) NOT NULL COMMENT '提供商标识，如 openrouter / together / azure / official',

    -- 提供商显示名称
    `name`       VARCHAR(200) NOT NULL COMMENT '显示名称',

    -- Logo 图片地址
    `logo_url`   TEXT         COMMENT 'Logo 图片地址',

    -- 是否启用
    `is_active`  TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用：1=启用 0=禁用',

    -- 时间戳
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_providers_slug` (`slug`),
    KEY `idx_providers_is_active` (`is_active`)

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='API 服务提供商（提供模型访问渠道的公司）';


-- ============================================================
-- 表6：模型-提供商报价配置
-- 记录每个模型在各提供商的价格、API 地址等配置
-- price_input_per_m / price_output_per_m 允许为 NULL（价格未知时先建立关联）
-- ============================================================
CREATE TABLE `model_provider_offerings` (

    -- 内部自增主键
    `id`                 BIGINT         NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 关联模型
    `model_id`           BIGINT         NOT NULL COMMENT '关联模型 ID（models.id）',

    -- 关联提供商
    `provider_id`        BIGINT         NOT NULL COMMENT '关联提供商 ID（providers.id）',

    -- 每百万输入 token 价格（人民币），NULL 表示价格未知
    `price_input_per_m`  DECIMAL(10, 4) COMMENT '每百万输入 token 价格（人民币，NULL=未知）',

    -- 每百万输出 token 价格（人民币），NULL 表示价格未知
    `price_output_per_m` DECIMAL(10, 4) COMMENT '每百万输出 token 价格（人民币，NULL=未知）',

    -- 在该提供商的模型名称（调用 API 时使用）
    `provider_model_id`  VARCHAR(200)   COMMENT '在该提供商的模型标识，如 openai/gpt-4o',

    -- API 基础地址（可选，留空则使用提供商默认地址）
    `api_base_url`       TEXT           COMMENT 'API 基础地址（空则使用提供商默认地址）',

    -- 价格最后更新时间
    `price_updated_at`   DATETIME       COMMENT '价格最后更新时间',

    -- 价格更新操作人（管理员邮箱或姓名）
    `price_updated_by`   VARCHAR(100)   COMMENT '价格更新人（管理员邮箱/名称）',

    -- 是否启用（禁用则不参与探测和展示）
    `is_active`          TINYINT(1)     NOT NULL DEFAULT 1 COMMENT '是否启用：1=启用 0=禁用',

    -- 时间戳
    `created_at`         DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`         DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    -- 同一模型在同一提供商只能有一条记录
    UNIQUE KEY `uk_mpo_model_provider` (`model_id`, `provider_id`),
    KEY `idx_mpo_model_id` (`model_id`),
    KEY `idx_mpo_provider_id` (`provider_id`),
    KEY `idx_mpo_is_active` (`is_active`),

    -- 外键：级联删除
    CONSTRAINT `fk_mpo_model_id`
        FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_mpo_provider_id`
        FOREIGN KEY (`provider_id`) REFERENCES `providers` (`id`) ON DELETE CASCADE

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='模型在各提供商的报价配置';


-- ============================================================
-- 表7：性能探测原始记录（append-only）
-- 只 INSERT 不 UPDATE；由 APScheduler 定时任务写入
-- 聚合查询通过 VIEW provider_metrics_ranked 完成
-- ============================================================
CREATE TABLE `provider_performance_metrics` (

    -- 内部自增主键
    `id`             BIGINT        NOT NULL AUTO_INCREMENT COMMENT '内部主键',

    -- 关联报价配置
    `offering_id`    BIGINT        NOT NULL COMMENT '关联报价 ID（model_provider_offerings.id）',

    -- 吞吐量：tokens/秒
    `throughput_tps` DECIMAL(8, 2) COMMENT '吞吐量（tokens/秒）',

    -- 首字延迟：毫秒
    `ttft_ms`        INT           COMMENT '首字延迟（毫秒）',

    -- 端到端延迟：毫秒
    `e2e_latency_ms` INT           COMMENT '端到端延迟（毫秒）',

    -- 本次探测是否成功
    `success`        TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否成功：1=成功 0=失败',

    -- 失败时的错误码（如 rate_limit / timeout / auth_error）
    `error_code`     VARCHAR(50)   COMMENT '错误码（失败时记录）',

    -- 本次探测的 prompt tokens 数
    `prompt_tokens`  INT           COMMENT '本次探测消耗的 prompt tokens',

    -- 本次探测的输出 tokens 数
    `output_tokens`  INT           COMMENT '本次探测产生的输出 tokens',

    -- 探测区域（支持多地域独立统计）
    `probe_region`   VARCHAR(50)   COMMENT '探测区域，如 cn-east / us-west',

    -- 探测时间
    `measured_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '探测时间',

    -- 主键和约束
    PRIMARY KEY (`id`),
    -- 复合索引：快速查询某 offering 的最新探测记录
    KEY `idx_ppm_offering_time` (`offering_id`, `measured_at` DESC),
    -- 支持按区域聚合查询
    KEY `idx_ppm_offering_region` (`offering_id`, `probe_region`),

    -- 外键：级联删除（删除 offering 时同步删除所有探测记录）
    CONSTRAINT `fk_ppm_offering_id`
        FOREIGN KEY (`offering_id`) REFERENCES `model_provider_offerings` (`id`) ON DELETE CASCADE

) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='性能探测原始记录（append-only，由定时任务写入）';


-- ============================================================
-- 视图：按 (offering_id, probe_region) 分区的排名视图
-- 只做排名，不做聚合；聚合 N 由应用层控制
-- 应用层查询示例：
--   SELECT offering_id, probe_region, AVG(throughput_tps), AVG(ttft_ms)
--   FROM provider_metrics_ranked
--   WHERE rn <= 5
--   GROUP BY offering_id, probe_region
-- 过滤规则：
--   1. 只包含 success=1 的记录
--   2. 只包含 is_active=1 的 offering（禁用 offering 不参与聚合）
-- ============================================================
CREATE VIEW `provider_metrics_ranked` AS
SELECT
    m.`offering_id`,
    m.`probe_region`,
    m.`throughput_tps`,
    m.`ttft_ms`,
    m.`e2e_latency_ms`,
    m.`measured_at`,
    ROW_NUMBER() OVER (
        PARTITION BY m.`offering_id`, m.`probe_region`
        ORDER BY m.`measured_at` DESC
    ) AS `rn`
FROM `provider_performance_metrics` m
WHERE m.`success` = 1
  AND m.`offering_id` IN (
      SELECT `id` FROM `model_provider_offerings` WHERE `is_active` = 1
  );
