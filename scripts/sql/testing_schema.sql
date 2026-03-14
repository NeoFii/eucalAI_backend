SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `model_categories` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `key` VARCHAR(50) NOT NULL COMMENT 'Category key',
    `name` VARCHAR(100) NOT NULL COMMENT 'Display name',
    `sort_order` SMALLINT NOT NULL DEFAULT 0 COMMENT 'Sort order',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether active',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_categories_key` (`key`),
    KEY `idx_model_categories_sort` (`sort_order`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model categories';

INSERT INTO `model_categories` (`key`, `name`, `sort_order`, `is_active`) VALUES
    ('reasoning', 'Reasoning and Planning', 1, 1),
    ('coding', 'Coding', 2, 1),
    ('tool_use', 'Tool Use', 3, 1),
    ('instruction_following', 'Instruction Following', 4, 1)
ON DUPLICATE KEY UPDATE
    `name` = VALUES(`name`),
    `sort_order` = VALUES(`sort_order`),
    `is_active` = VALUES(`is_active`);

CREATE TABLE IF NOT EXISTS `model_vendors` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `slug` VARCHAR(100) NOT NULL COMMENT 'Vendor slug',
    `name` VARCHAR(200) NOT NULL COMMENT 'Display name',
    `logo_url` TEXT NULL COMMENT 'Logo URL',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether active',
    `deleted_at` DATETIME NULL COMMENT 'Soft delete time',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_vendors_slug` (`slug`),
    KEY `idx_model_vendors_is_active` (`is_active`),
    KEY `idx_model_vendors_deleted_at` (`deleted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model vendors';

CREATE TABLE IF NOT EXISTS `models` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `vendor_id` BIGINT NOT NULL COMMENT 'Vendor id',
    `slug` VARCHAR(100) NOT NULL COMMENT 'Model slug',
    `name` VARCHAR(200) NOT NULL COMMENT 'Display name',
    `description` TEXT NULL COMMENT 'Description',
    `capability_tags` JSON NOT NULL COMMENT 'Capability tags',
    `context_window` INT NULL COMMENT 'Context window',
    `max_output_tokens` INT NULL COMMENT 'Max output tokens',
    `is_reasoning_model` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Reasoning model flag',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Sort order',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether active',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_models_slug` (`slug`),
    KEY `idx_models_vendor_id` (`vendor_id`),
    KEY `idx_models_is_active` (`is_active`),
    KEY `idx_models_sort_order` (`sort_order`),
    CONSTRAINT `fk_models_vendor_id` FOREIGN KEY (`vendor_id`) REFERENCES `model_vendors` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Models';

CREATE TABLE IF NOT EXISTS `model_category_map` (
    `model_id` BIGINT NOT NULL COMMENT 'Model id',
    `category_id` BIGINT NOT NULL COMMENT 'Category id',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT 'Sort order in category',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    PRIMARY KEY (`model_id`, `category_id`),
    KEY `idx_mcm_category_sort` (`category_id`, `sort_order`),
    CONSTRAINT `fk_mcm_model_id` FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_mcm_category_id` FOREIGN KEY (`category_id`) REFERENCES `model_categories` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model category map';

CREATE TABLE IF NOT EXISTS `providers` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `slug` VARCHAR(100) NOT NULL COMMENT 'Provider slug',
    `name` VARCHAR(200) NOT NULL COMMENT 'Display name',
    `logo_url` TEXT NULL COMMENT 'Logo URL',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether active',
    `deleted_at` DATETIME NULL COMMENT 'Soft delete time',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_providers_slug` (`slug`),
    KEY `idx_providers_is_active` (`is_active`),
    KEY `idx_providers_deleted_at` (`deleted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API providers';

CREATE TABLE IF NOT EXISTS `provider_probe_configs` (
    `provider_id` BIGINT NOT NULL COMMENT 'Provider id',
    `probe_api_base_url` TEXT NULL COMMENT 'Probe API base URL',
    `probe_api_key_ciphertext` TEXT NULL COMMENT 'Encrypted API key',
    `probe_api_key_iv` TEXT NULL COMMENT 'API key IV',
    `probe_api_key_tag` TEXT NULL COMMENT 'API key tag',
    `probe_api_key_masked` VARCHAR(50) NULL COMMENT 'Masked API key',
    `probe_key_updated_at` DATETIME NULL COMMENT 'Probe key updated at',
    `key_updated_by_admin_id` BIGINT NULL COMMENT 'Key updater admin id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`provider_id`),
    CONSTRAINT `fk_provider_probe_configs_provider_id` FOREIGN KEY (`provider_id`) REFERENCES `providers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Provider probe configs';

CREATE TABLE IF NOT EXISTS `model_provider_offerings` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `model_id` BIGINT NOT NULL COMMENT 'Model id',
    `provider_id` BIGINT NOT NULL COMMENT 'Provider id',
    `price_input_per_m` DECIMAL(10, 4) NULL COMMENT 'Input price per million tokens',
    `price_output_per_m` DECIMAL(10, 4) NULL COMMENT 'Output price per million tokens',
    `api_base_url` TEXT NULL COMMENT 'Legacy per-offering API base URL',
    `price_updated_at` DATETIME NULL COMMENT 'Price updated at',
    `price_updated_by` VARCHAR(100) NULL COMMENT 'Legacy price updater label',
    `price_updated_by_admin_id` BIGINT NULL COMMENT 'Price updater admin id',
    `provider_model_name` VARCHAR(200) NULL COMMENT 'Provider-side model name',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether active',
    `deleted_at` DATETIME NULL COMMENT 'Soft delete time',
    `created_by_admin_id` BIGINT NULL COMMENT 'Creator admin id',
    `updated_by_admin_id` BIGINT NULL COMMENT 'Updater admin id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_mpo_model_provider` (`model_id`, `provider_id`),
    KEY `idx_mpo_model_id` (`model_id`),
    KEY `idx_mpo_provider_id` (`provider_id`),
    KEY `idx_mpo_is_active` (`is_active`),
    KEY `idx_mpo_deleted_at` (`deleted_at`),
    CONSTRAINT `fk_mpo_model_id` FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_mpo_provider_id` FOREIGN KEY (`provider_id`) REFERENCES `providers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model provider offerings';

CREATE TABLE IF NOT EXISTS `provider_performance_metrics` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `offering_id` BIGINT NOT NULL COMMENT 'Offering id',
    `throughput_tps` DECIMAL(8, 2) NULL COMMENT 'Throughput in tokens/s',
    `ttft_ms` INT NULL COMMENT 'Time to first token in ms',
    `e2e_latency_ms` INT NULL COMMENT 'End-to-end latency in ms',
    `success` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether success',
    `error_code` VARCHAR(50) NULL COMMENT 'Failure code',
    `prompt_tokens` INT NULL COMMENT 'Prompt tokens',
    `output_tokens` INT NULL COMMENT 'Output tokens',
    `probe_region` VARCHAR(50) NULL COMMENT 'Probe region',
    `measured_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Measured at',
    PRIMARY KEY (`id`),
    KEY `idx_ppm_offering_time` (`offering_id`, `measured_at`),
    KEY `idx_ppm_offering_region` (`offering_id`, `probe_region`),
    KEY `idx_ppm_success_time` (`success`, `measured_at`),
    CONSTRAINT `fk_ppm_offering_id` FOREIGN KEY (`offering_id`) REFERENCES `model_provider_offerings` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Probe performance metrics';

CREATE TABLE IF NOT EXISTS `provider_performance_daily_stats` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `offering_id` BIGINT NOT NULL COMMENT 'Offering id',
    `probe_region` VARCHAR(50) NOT NULL COMMENT 'Probe region',
    `stat_date` DATE NOT NULL COMMENT 'Stat date',
    `sample_count` INT NOT NULL DEFAULT 0 COMMENT 'Sample count',
    `success_count` INT NOT NULL DEFAULT 0 COMMENT 'Success count',
    `fail_count` INT NOT NULL DEFAULT 0 COMMENT 'Fail count',
    `avg_throughput_tps` DECIMAL(10, 2) NULL COMMENT 'Average throughput',
    `avg_ttft_ms` INT NULL COMMENT 'Average TTFT',
    `avg_e2e_latency_ms` INT NULL COMMENT 'Average E2E latency',
    `min_throughput_tps` DECIMAL(10, 2) NULL COMMENT 'Min throughput',
    `max_throughput_tps` DECIMAL(10, 2) NULL COMMENT 'Max throughput',
    `min_ttft_ms` INT NULL COMMENT 'Min TTFT',
    `max_ttft_ms` INT NULL COMMENT 'Max TTFT',
    `last_measured_at` DATETIME NULL COMMENT 'Last measured at',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_provider_performance_daily_stats` (`offering_id`, `probe_region`, `stat_date`),
    KEY `idx_ppds_date` (`stat_date`),
    KEY `idx_ppds_offering_date` (`offering_id`, `stat_date`),
    CONSTRAINT `fk_ppds_offering_id` FOREIGN KEY (`offering_id`) REFERENCES `model_provider_offerings` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Daily performance stats';

CREATE TABLE IF NOT EXISTS `benchmark_jobs` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `job_id` VARCHAR(64) NOT NULL COMMENT 'Public benchmark job id',
    `job_type` VARCHAR(16) NOT NULL COMMENT 'full/single',
    `status` VARCHAR(20) NOT NULL DEFAULT 'queued' COMMENT 'queued/running/succeeded/failed/partial',
    `requested_by_admin_id` BIGINT NULL COMMENT 'Triggering admin id',
    `scope_offering_id` BIGINT NULL COMMENT 'Target offering id for single probe',
    `trigger_source` VARCHAR(20) NOT NULL DEFAULT 'manual' COMMENT 'manual/scheduler',
    `total_offerings` INT NOT NULL DEFAULT 0 COMMENT 'Total offerings in this job',
    `completed_offerings` INT NOT NULL DEFAULT 0 COMMENT 'Completed offerings count',
    `succeeded_offerings` INT NOT NULL DEFAULT 0 COMMENT 'Succeeded offerings count',
    `failed_offerings` INT NOT NULL DEFAULT 0 COMMENT 'Failed offerings count',
    `queued_at` DATETIME NULL COMMENT 'Queued at',
    `started_at` DATETIME NULL COMMENT 'Started at',
    `finished_at` DATETIME NULL COMMENT 'Finished at',
    `error_message` TEXT NULL COMMENT 'Last job error message',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_benchmark_jobs_job_id` (`job_id`),
    KEY `idx_benchmark_jobs_status` (`status`),
    KEY `idx_benchmark_jobs_job_type` (`job_type`),
    KEY `idx_benchmark_jobs_requested_by` (`requested_by_admin_id`),
    KEY `idx_benchmark_jobs_scope_offering` (`scope_offering_id`),
    KEY `idx_benchmark_jobs_created_at` (`created_at`),
    CONSTRAINT `fk_benchmark_jobs_scope_offering` FOREIGN KEY (`scope_offering_id`) REFERENCES `model_provider_offerings` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Benchmark dispatch jobs';

CREATE TABLE IF NOT EXISTS `admin_probe_audit_logs` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
    `job_id` VARCHAR(64) NOT NULL COMMENT 'Benchmark job id',
    `offering_id` BIGINT NULL COMMENT 'Offering id',
    `model_id` BIGINT NULL COMMENT 'Model id',
    `provider_id` BIGINT NULL COMMENT 'Provider id',
    `triggered_by_admin_id` BIGINT NULL COMMENT 'Triggering admin id',
    `status` VARCHAR(20) NOT NULL COMMENT 'completed/failed',
    `success` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether the manual probe succeeded',
    `error_code` VARCHAR(128) NULL COMMENT 'Failure code',
    `ttft_ms` INT NULL COMMENT 'Time to first token in ms',
    `e2e_latency_ms` INT NULL COMMENT 'End-to-end latency in ms',
    `throughput_tps` DECIMAL(10, 2) NULL COMMENT 'Throughput in tokens/s',
    `prompt_tokens` INT NULL COMMENT 'Prompt token count',
    `output_tokens` INT NULL COMMENT 'Output token count',
    `probe_region` VARCHAR(50) NULL COMMENT 'Probe region',
    `started_at` DATETIME NULL COMMENT 'Started at',
    `finished_at` DATETIME NULL COMMENT 'Finished at',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (`id`),
    KEY `idx_admin_probe_audits_job_id` (`job_id`),
    KEY `idx_admin_probe_audits_offering_id` (`offering_id`),
    KEY `idx_admin_probe_audits_admin_id` (`triggered_by_admin_id`),
    KEY `idx_admin_probe_audits_created_at` (`created_at`),
    CONSTRAINT `fk_admin_probe_audits_offering_id` FOREIGN KEY (`offering_id`) REFERENCES `model_provider_offerings` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_admin_probe_audits_model_id` FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_admin_probe_audits_provider_id` FOREIGN KEY (`provider_id`) REFERENCES `providers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Admin manual probe audit logs';

CREATE OR REPLACE VIEW `provider_metrics_ranked` AS
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
JOIN `model_provider_offerings` o
  ON o.`id` = m.`offering_id`
WHERE m.`success` = 1
  AND o.`is_active` = 1
  AND o.`deleted_at` IS NULL;

SET FOREIGN_KEY_CHECKS = 1;
