-- -*- coding: utf-8 -*-
-- Testing 服务数据库初始化脚本
-- 创建表结构和基础数据

-- 模型分类表
CREATE TABLE IF NOT EXISTS model_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name_zh VARCHAR(50) NOT NULL COMMENT '中文名称',
    name_en VARCHAR(50) NOT NULL COMMENT '英文名称',
    slug VARCHAR(50) NOT NULL UNIQUE COMMENT '英文别名',
    description_zh TEXT COMMENT '中文描述',
    description_en TEXT COMMENT '英文描述',
    icon VARCHAR(50) COMMENT '图标标识',
    sort_order INT DEFAULT 0 COMMENT '排序顺序',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型分类';

-- 模型表
CREATE TABLE IF NOT EXISTS models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id VARCHAR(100) NOT NULL UNIQUE COMMENT '对外模型ID',
    name VARCHAR(100) NOT NULL COMMENT '显示名称',
    name_zh VARCHAR(100) COMMENT '中文名称',
    description_zh TEXT COMMENT '中文描述',
    description_en TEXT COMMENT '英文描述',
    context_length INT DEFAULT 0 COMMENT '上下文长度',
    model_size VARCHAR(50) COMMENT '模型大小',
    is_open_source BOOLEAN DEFAULT FALSE COMMENT '是否开源',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型基础信息';

-- 模型-分类关联表
CREATE TABLE IF NOT EXISTS model_category_mapping (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id INT NOT NULL COMMENT '模型ID',
    category_id INT NOT NULL COMMENT '分类ID',
    is_primary BOOLEAN DEFAULT FALSE COMMENT '是否为主分类',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES model_categories(id) ON DELETE CASCADE,
    UNIQUE KEY uk_model_category (model_id, category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型-分类关联';

-- 模型标签表
CREATE TABLE IF NOT EXISTS model_tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id INT NOT NULL COMMENT '模型ID',
    tag VARCHAR(50) NOT NULL COMMENT '标签名',
    tag_type VARCHAR(20) DEFAULT 'feature' COMMENT '标签类型',
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    INDEX idx_model_tags_model_id (model_id),
    INDEX idx_model_tags_tag (tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型标签';

-- 供应商表
CREATE TABLE IF NOT EXISTS providers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    provider_id VARCHAR(50) NOT NULL UNIQUE COMMENT '供应商ID',
    name VARCHAR(100) NOT NULL COMMENT '显示名称',
    name_zh VARCHAR(100) COMMENT '中文名称',
    logo_url VARCHAR(255) COMMENT 'Logo URL',
    color VARCHAR(20) COMMENT '主题色',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    sort_order INT DEFAULT 0 COMMENT '排序顺序',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='供应商';

-- 模型-供应商关联表
CREATE TABLE IF NOT EXISTS model_providers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id INT NOT NULL COMMENT '模型ID',
    provider_id INT NOT NULL COMMENT '供应商ID',
    api_model_name VARCHAR(200) NOT NULL COMMENT '供应商API模型名',
    routing_alias VARCHAR(100) COMMENT '路由别名',
    input_price_cny_1m DECIMAL(10, 4) COMMENT '每百万输入价格(人民币)',
    output_price_cny_1m DECIMAL(10, 4) COMMENT '每百万输出价格(人民币)',
    rate_limit_rpm INT DEFAULT 60 COMMENT '供应商限速(每分钟请求数)',
    is_default BOOLEAN DEFAULT FALSE COMMENT '是否默认供应商',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    UNIQUE KEY uk_model_provider (model_id, provider_id),
    INDEX idx_model_providers_model_id (model_id),
    INDEX idx_model_providers_provider_id (provider_id),
    INDEX idx_model_providers_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型-供应商关联';

-- 性能测试结果表
CREATE TABLE IF NOT EXISTS benchmark_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_provider_id INT NOT NULL COMMENT '模型供应商ID',
    latency_ttft DECIMAL(10, 4) COMMENT '首字延迟(秒)',
    latency_total DECIMAL(10, 4) COMMENT '总延迟(秒)',
    throughput DECIMAL(10, 2) COMMENT '吞吐量(tokens/秒)',
    success_count INT DEFAULT 0 COMMENT '成功次数',
    fail_count INT DEFAULT 0 COMMENT '失败次数',
    test_prompt VARCHAR(500) COMMENT '测试使用的prompt',
    test_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_provider_id) REFERENCES model_providers(id) ON DELETE CASCADE,
    INDEX idx_benchmark_results_model_provider_id (model_provider_id),
    INDEX idx_benchmark_results_test_at (test_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='性能测试结果';

-- 插入基础分类数据
INSERT INTO model_categories (name_zh, name_en, slug, description_zh, description_en, icon, sort_order) VALUES
('逻辑推理与规划', 'Reasoning & Planning', 'reasoning', '擅长逻辑推理、数学计算、问题分析解决的模型', 'Models specialized in logical reasoning, math, and problem solving', 'brain', 1),
('编程', 'Programming', 'coding', '擅长代码生成、代码补全、代码优化的模型', 'Models specialized in code generation, completion and optimization', 'code', 2),
('工具调用', 'Tool Calling', 'tool_use', '支持调用外部工具和函数的模型', 'Models that support external tool and function calling', 'tool', 3),
('复杂指令遵循', 'Complex Instruction Following', 'complex_instruction', '擅长理解复杂指令、执行多步骤任务的模型', 'Models specialized in understanding complex instructions and multi-step tasks', 'list-check', 4);

-- 插入示例供应商数据
INSERT INTO providers (provider_id, name, name_zh, color, sort_order) VALUES
('aliyun', '阿里云', 'Aliyun', '#ff6a00', 1),
('siliconflow', '硅基流动', 'SiliconFlow', '#4f46e5', 2),
('deepseek', 'DeepSeek', 'DeepSeek', '#4a90e2', 3),
('openai', 'OpenAI', 'OpenAI', '#10a37f', 4);
