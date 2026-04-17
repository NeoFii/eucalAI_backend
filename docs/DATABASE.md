# Eucal AI Backend — 数据表关系文档

> 更新：2026-04-17
> 范围：`F:\Eucal_AI\backend`（对应 `src/<service>/models/`、`migrations/<service>/versions/`）

---

## 1. 总览

后端共 **4 个 MySQL 库**，每个库由一个服务独占写入。router-service 是 ML 推理服务，**没有库**。

| 数据库 | Owner | 作用 |
|---|---|---|
| `eucal_ai_admin` | admin-service | 管理员账户 / 邀请码 / 管理员操作审计 |
| `eucal_ai_user` | user-service | 终端用户账户 / 登录会话 / 邮箱验证码 |
| `eucal_ai_content` | content-service | 新闻 CRUD |
| `eucal_ai_testing` | testing-service | 模型目录 / 供应商 / 报价 / 基准测试作业与指标 |

**跨库外键一律禁止**。跨域引用靠应用层解析（HMAC 内部 API 或裸字段存 id/uid），详见 §6。

ID 惯例：所有业务表 `id` 是 `BigInteger`，由 `SnowflakeIdMixin` 生成雪花 ID；对外暴露字段叫 `uid`、`slug`、`code`、`session_id` 等（看语义）；审计日志、连接表、验证码类表用 `autoincrement=True` 的普通 BIGINT。

时间戳惯例：`TimestampMixin` 注入 `created_at` / `updated_at`；所有 `DateTime` **UTC naive 存储**，应用层负责时区转换（迁 Postgres `TIMESTAMPTZ` 时重审）。

---

## 2. admin 库（`eucal_ai_admin`）

### 2.1 ER 关系图

```
┌───────────────────────────────────────────┐
│              admin_users                  │
│ PK  id                                    │
│ UK  uid                                   │
│ UK  email                                 │
│     password_hash, name, status, role     │
│ FK→ created_by_admin_id    ─┐ (自引用)    │
│ FK→ updated_by_admin_id    ─┤            │
│ FK→ password_changed_by_admin_id ─┘       │
│     last_login_*, login_fail_count, …     │
└──────┬──────────────┬─────────────┬───────┘
       │              │             │
       │              │             │
       │   ┌──────────▼─────────┐   │   ┌──────────────────────────┐
       │   │  invitation_codes  │   │   │     admin_audit_logs     │
       │   │ PK id              │   │   │ PK id                    │
       │   │ UK code            │   │   │ FK actor_admin_id (NN)   │◄──┐
       │   │ FK→ created_by     │◄──┤   │ FK target_admin_id (N)   │◄──┤
       │   │    used_by (UID,   │   │   │    action, resource_type │   │
       │   │    no FK, 跨库→user)│   │   │    status, before/after  │   │
       │   │    status, expires │   │   │    reason, ip, ua         │   │
       │   └────────────────────┘   │   └──────────────────────────┘   │
       │                            │                                  │
       └────────────────────────────┴──────────────────────────────────┘
                                     (actor/target 都指向 admin_users)
```

### 2.2 表清单

#### `admin_users`

管理员账户。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | 内部主键 |
| `uid` | BIGINT | UNIQUE | 对外暴露的 UID |
| `email` | VARCHAR(255) | UNIQUE | 登录邮箱 |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt |
| `name` | VARCHAR(100) | NOT NULL | 昵称 |
| `status` | SMALLINT | DEFAULT 1 | 0=disabled 1=active |
| `role` | VARCHAR(20) | DEFAULT 'admin' | `admin` / `super_admin` |
| `created_by_admin_id` | BIGINT FK→admin_users.id | ON DELETE SET NULL | 创建者 |
| `updated_by_admin_id` | BIGINT FK→admin_users.id | ON DELETE SET NULL | 最后修改者 |
| `password_changed_by_admin_id` | BIGINT FK→admin_users.id | ON DELETE SET NULL | 最后改密者 |
| `password_changed_at` | DATETIME | NULL | 最后改密时间 |
| `last_login_at`, `last_login_ip` | DATETIME / VARCHAR(45) | NULL | 最后登录审计 |
| `login_fail_count` | INT | DEFAULT 0 | 连续失败次数 |
| `login_locked_until` | DATETIME | NULL | 登录锁定到期时间 |
| `created_at`, `updated_at` | DATETIME | NOT NULL | Mixin |

**自引用**：`created_by_admin_id` / `updated_by_admin_id` / `password_changed_by_admin_id` 都指回 `admin_users.id`，形成 3 条自引用关系（`created_by_admin` / `updated_by_admin` / `password_changed_by_admin`）。

#### `invitation_codes`

邀请码。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | — |
| `code` | VARCHAR(64) | UNIQUE | 邀请码明文 |
| `status` | SMALLINT | DEFAULT 0 | 0=unused 1=used 2=disabled |
| `created_by` | BIGINT FK→admin_users.id | ON DELETE SET NULL, INDEXED | 发码管理员 |
| `used_by` | BIGINT | INDEXED, **不加 FK** | 使用者 user UID（**跨库**，见 §6） |
| `used_at` | DATETIME | NULL | 使用时间 |
| `expires_at` | DATETIME | NULL | 有效期 |
| `remark` | TEXT | NULL | 备注 |
| `created_at`, `updated_at` | — | — | Mixin |

`used_by` 存的是 user 库里的 `users.uid`，**不是 `users.id`**。历史原因：注册流程先 claim 邀请码再提交 user 行，拿不到 user.id。

#### `admin_audit_logs`

管理员操作审计。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `actor_admin_id` | BIGINT FK→admin_users.id | ON DELETE **RESTRICT**, NOT NULL, INDEXED | 操作者；**不许删** |
| `target_admin_id` | BIGINT FK→admin_users.id | ON DELETE SET NULL, NULL, INDEXED | 被操作管理员；可空 |
| `action` | VARCHAR(100) | NOT NULL, INDEXED | 操作代码 |
| `resource_type` | VARCHAR(50) | NOT NULL, INDEXED | 资源类型 |
| `resource_id` | VARCHAR(100) | NULL | 资源 ID（字符串，可跨库） |
| `status` | VARCHAR(20) | NOT NULL | `success` / `failed` |
| `before_data`, `after_data` | JSON | NULL | 前后快照 |
| `reason` | VARCHAR(255) | NULL | 失败/补充 |
| `ip_address`, `user_agent` | VARCHAR(45) / VARCHAR(512) | NULL | 来源审计 |
| `created_at` | DATETIME | NOT NULL, DEFAULT now | 事件时间（无 updated_at） |

`actor_admin_id` 是 RESTRICT 而不是 CASCADE/SET NULL：任何管理员只要留有审计就不能硬删除，保合规完整性。

---

## 3. user 库（`eucal_ai_user`）

### 3.1 ER 关系图

```
┌────────────────────────────────┐
│           users                │
│ PK  id                         │
│ UK  uid                        │
│ UK  email                      │
│     password_hash, status, ... │
└───────┬────────────────┬───────┘
        │                │
        │                │
        │    ┌───────────▼──────────────────────┐
        │    │        user_sessions             │
        │    │ PK id                            │
        │    │ UK session_id                    │
        │    │ UK token_jti                     │
        │    │ FK user_id (CASCADE)             │
        │    │    refresh_token_hash, expires,  │
        │    │    revoked_at, ua, ip            │
        │    └───────────┬──────────────────────┘
        │                │
        │                │ (1:1)
        │                │
        │   ┌────────────▼────────────────────┐
        └───┤      user_active_sessions       │
            │ PK  user_id (FK→users, CASCADE) │
            │ UK  session_id                  │
            │     (FK→user_sessions.session_id│
            │      CASCADE)                   │
            │     updated_at                  │
            └─────────────────────────────────┘

┌──────────────────────────────────────┐
│      email_verification_codes        │
│ PK id (自增)                         │
│    email, code_hash, purpose,        │
│    expires_at, used_at, error_count  │
│   (与 users 无 FK；按 email 关联)    │
└──────────────────────────────────────┘
```

### 3.2 表清单

#### `users`

终端用户账户。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | — |
| `uid` | BIGINT | UNIQUE | 对外 UID |
| `email` | VARCHAR(255) | UNIQUE | 写入前 lowercase + trim（迁 Postgres 免大小写坑） |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt |
| `status` | SMALLINTEGER | DEFAULT 1 | 0=disabled 1=active 2=pending |
| `email_verified_at` | DATETIME | NULL | 验证时间 |
| `last_login_at`, `last_login_ip` | — | NULL | 登录审计 |
| `login_fail_count` | INT | DEFAULT 0 | 连续失败次数 |
| `login_locked_until` | DATETIME | NULL | 锁定到期 |
| `created_at`, `updated_at` | — | — | Mixin |

#### `user_sessions`

refresh-token 会话。一个用户可以有多条（各设备），但只有一条在 `user_active_sessions` 里标记"当前活跃"。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | — |
| `session_id` | BIGINT | UNIQUE | 对外会话 id |
| `user_id` | BIGINT FK→users.id | **ON DELETE CASCADE**, INDEXED | 删除用户会级联 |
| `token_jti` | VARCHAR(64) | UNIQUE | refresh token 的 jti 哈希 |
| `refresh_token_hash` | VARCHAR(255) | NOT NULL | refresh token 哈希 |
| `user_agent`, `ip_address` | VARCHAR(512) / VARCHAR(45) | NULL | 来源审计 |
| `expires_at` | DATETIME | NOT NULL | 到期 |
| `revoked_at` | DATETIME | NULL | 撤销时间；为 NULL 表示未撤销 |
| `created_at`, `updated_at` | — | — | Mixin |

#### `user_active_sessions`

每个用户最多一条活跃会话的映射（登录互踢语义）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `user_id` | BIGINT PK, FK→users.id | ON DELETE CASCADE | 同时是主键 |
| `session_id` | BIGINT, FK→user_sessions.session_id | ON DELETE CASCADE, UNIQUE | 指向"当前活跃"那一条 |
| `updated_at` | DATETIME | DEFAULT/ONUPDATE now | 最后活跃时间 |

> 注意：这里的 FK 目标是 `user_sessions.session_id`（UK），不是 `user_sessions.id`（PK）。

#### `email_verification_codes`

邮箱验证码（注册、找回密码等）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `email` | VARCHAR(255) | NOT NULL | 目标邮箱（**不加 FK** 到 users） |
| `code_hash` | VARCHAR(255) | NOT NULL | 验证码哈希 |
| `purpose` | VARCHAR(20) | NOT NULL, DEFAULT 'register' | `register` / `reset_password` / ... |
| `expires_at` | DATETIME | NOT NULL | 过期 |
| `used_at` | DATETIME | NULL | 已使用 |
| `error_count` | INT | DEFAULT 0 | 错误累计 |
| `locked_until` | DATETIME | NULL | 锁定到期 |
| `created_at` | DATETIME | DEFAULT now | 无 updated_at |

索引：`idx_codes_email`、`idx_codes_email_purpose`、`idx_codes_expires_at`。

---

## 4. content 库（`eucal_ai_content`）

### 4.1 表清单

只有一张表。

#### `news`

新闻内容。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | — |
| `uid` | BIGINT | UNIQUE | 对外 UID |
| `title` | VARCHAR(255) | NOT NULL | — |
| `slug` | VARCHAR(255) | UNIQUE (`uk_news_slug`) | URL 友好标识 |
| `summary` | VARCHAR(500) | NULL | 摘要 |
| `cover_image` | VARCHAR(500) | NULL | 封面图 URL |
| `content` | TEXT (utf8mb4_unicode_ci) | NOT NULL | Markdown 正文 |
| `status` | SMALLINT | DEFAULT 0 | 0=draft 1=published 2=offline 3=deleted |
| `published_at` | DATETIME | NULL | 发布时间 |
| `author_id` | BIGINT | NULL, **无 FK** | 作者 admin id（**跨库**，见 §6） |
| `deleted_at` | DATETIME | NULL | 软删时间 |
| `deleted_by_admin_id` | BIGINT | NULL, **无 FK** | 软删操作管理员 id（**跨库**） |
| `created_at`, `updated_at` | — | — | Mixin |

复合索引：`idx_status_published(status, published_at)` 供前台列表；`idx_news_deleted_at` 供回收站/清理脚本。

---

## 5. testing 库（`eucal_ai_testing`）

这是体积最大、关系最密的库。

### 5.1 ER 关系图

```
┌──────────────┐     ┌──────────────┐     ┌────────────────────┐
│model_categor.│     │model_vendors │     │     providers      │
│ id (PK)      │     │ id (PK)      │     │ id (PK)            │
│ UK key       │     │ UK slug      │     │ UK slug            │
└──────┬───────┘     │ logo, active │     │ logo, active       │
       │             │ deleted_at   │     │ deleted_at         │
       │             └──────┬───────┘     └─┬──────────┬───────┘
       │                    │               │          │
       │                    │               │ (1:1)    │
       │                    │               │          │
       │                    │       ┌───────▼──────────┴────────┐
       │                    │       │ provider_probe_configs    │
       │                    │       │ PK provider_id (FK)       │
       │                    │       │    probe_api_*, _masked   │
       │                    │       └───────────────────────────┘
       │                    │
       │                    │
       │              ┌─────▼──────────────────┐
       │              │        models          │
       │              │ id (PK)                │
       │              │ UK slug                │
       │              │ FK vendor_id           │
       │              │    name, description,  │
       │              │    capability_tags JSON│
       │              │    context_window, ... │
       │              └─────┬──────────────────┘
       │                    │
       │                    │
┌──────▼──────────┐         │
│model_category_  │         │
│     map         │         │
│ PK (model_id,   │◄────────┘
│     category_id)│
│    sort_order   │
└─────────────────┘         
                            
                            ┌───────────────────────────────┐
                            │   model_provider_offerings    │
                            │ id (PK)                       │
                            │ FK model_id (CASCADE)         │◄── models.id
                            │ FK provider_id (CASCADE)      │◄── providers.id
                            │ UK (model_id, provider_id)    │
                            │    price_input/output_per_m   │
                            │    api_base_url, is_active,   │
                            │    deleted_at                 │
                            │    *_by_admin_id (跨库)       │
                            └─┬─────────────┬───────────────┘
                              │             │
                              │             │
               ┌──────────────▼──┐    ┌─────▼──────────────────────────┐
               │ provider_       │    │ provider_performance_          │
               │ performance_    │    │   daily_stats                  │
               │   metrics       │    │ id (PK)                        │
               │ id (PK)         │    │ FK offering_id (CASCADE)       │
               │ FK offering_id  │    │ UK (offering_id, probe_region, │
               │    (CASCADE)    │    │     stat_date)                 │
               │    throughput,  │    │    sample_count, success/fail, │
               │    ttft, e2e,   │    │    avg_* / min_* / max_*       │
               │    success,     │    └────────────────────────────────┘
               │    measured_at  │
               └─────────────────┘

┌───────────────────────────────────┐
│        benchmark_jobs             │
│ id (PK)                           │
│ UK job_id                         │
│ FK scope_offering_id (SET NULL)   │◄── model_provider_offerings.id
│    job_type, status, counts,      │
│    trigger_source,                │
│    requested_by_admin_id (跨库)   │
│    queued/started/finished_at     │
└───────────────────────────────────┘

┌───────────────────────────────────┐
│     admin_probe_audit_logs        │
│ id (PK)                           │
│    job_id (字符串，指 benchmark_  │
│             jobs.job_id，无 FK)   │
│ FK offering_id (SET NULL)         │
│ FK model_id    (SET NULL)         │
│ FK provider_id (SET NULL)         │
│    triggered_by_admin_id (跨库)   │
│    status, success, metrics, …    │
└───────────────────────────────────┘

┌───────────────────────────────────┐
│     provider_metrics_ranked       │  （VIEW，非表）
│  offering_id, probe_region,       │
│  measured_at, throughput_tps,     │
│  ttft_ms, e2e_latency_ms, rn      │
└───────────────────────────────────┘
```

### 5.2 表清单

#### `model_categories`

模型分类字典表。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `key` | VARCHAR(50) | UNIQUE, NOT NULL | 分类键（机读） |
| `name` | VARCHAR(100) | NOT NULL | 显示名 |
| `sort_order` | SMALLINT | DEFAULT 0 | 排序 |
| `is_active` | BOOL | DEFAULT true | — |
| `created_at`, `updated_at` | — | — | Mixin |

#### `model_vendors`

模型厂商（OpenAI、Anthropic、…）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `slug` | VARCHAR(100) | UNIQUE | 机读标识 |
| `name` | VARCHAR(200) | NOT NULL | 显示名 |
| `logo_url` | TEXT | NULL | Logo |
| `is_active` | BOOL | DEFAULT true | — |
| `deleted_at` | DATETIME | NULL | 软删 |
| `created_at`, `updated_at` | — | — | Mixin |

索引：`idx_model_vendors_is_active`、`idx_model_vendors_deleted_at`。

#### `models`

模型（模型家族的一个具体版本）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `vendor_id` | BIGINT FK→model_vendors.id | NOT NULL | — |
| `slug` | VARCHAR(100) | UNIQUE | — |
| `name` | VARCHAR(200) | NOT NULL | — |
| `description` | TEXT | NULL | — |
| `capability_tags` | JSON | NOT NULL | `list[str]`。迁 PG 时升 JSONB 支持 GIN |
| `context_window` | INT | NULL | 上下文长度 |
| `max_output_tokens` | INT | NULL | — |
| `is_reasoning_model` | BOOL | DEFAULT false | 推理模型标记 |
| `sort_order`, `is_active` | INT / BOOL | — | — |
| `created_at`, `updated_at` | — | — | Mixin |

索引：`idx_models_vendor_id`、`idx_models_is_active`、`idx_models_sort_order`。

#### `model_category_map`

多对多连接表（模型 ↔ 分类）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `model_id` | BIGINT FK→models.id | **PK 之一**，ON DELETE CASCADE | — |
| `category_id` | BIGINT FK→model_categories.id | **PK 之一**，ON DELETE CASCADE | — |
| `sort_order` | INT | DEFAULT 0 | 该模型在该分类中的排序 |
| `created_at` | DATETIME | DEFAULT now | — |

复合主键 = `(model_id, category_id)`。索引 `idx_mcm_category_sort(category_id, sort_order)`。

#### `providers`

推理服务提供商（用来跑模型的上游 endpoint：OpenAI API、OpenRouter、Together、自建 vLLM ...）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `slug` | VARCHAR(100) | UNIQUE | 机读标识 |
| `name` | VARCHAR(200) | NOT NULL | 显示名 |
| `logo_url` | TEXT | NULL | — |
| `is_active`, `deleted_at` | — | — | 软删 |
| `created_at`, `updated_at` | — | — | Mixin |

索引：`idx_providers_is_active`、`idx_providers_deleted_at`。

#### `provider_probe_configs`

Provider 的探测 / 基准测试凭据（从 `providers` 表分出，因为含加密字段且不是总要用）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `provider_id` | BIGINT PK, FK→providers.id | **同时是主键**，ON DELETE CASCADE | 1:1 到 providers |
| `probe_api_base_url` | TEXT | NULL | — |
| `probe_api_key_ciphertext` | TEXT | NULL | AES-GCM 密文 |
| `probe_api_key_iv` | TEXT | NULL | IV |
| `probe_api_key_tag` | TEXT | NULL | Auth tag |
| `probe_api_key_masked` | VARCHAR(50) | NULL | 面向 UI 的遮罩 |
| `probe_key_updated_at` | DATETIME | NULL | — |
| `key_updated_by_admin_id` | BIGINT | NULL, **跨库无 FK** | 密钥更换操作 admin id |
| `created_at`, `updated_at` | — | — | Mixin |

ORM 层用 `@property` 把这些字段"穿透"到 Provider 上，代码读写 `provider.probe_api_base_url` 自动拿/写到 `provider_probe_configs`。

#### `model_provider_offerings`

**核心表**：某模型在某 provider 上的报价 / 接入方式。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `model_id` | BIGINT FK→models.id | ON DELETE CASCADE, NOT NULL | — |
| `provider_id` | BIGINT FK→providers.id | ON DELETE CASCADE, NOT NULL | — |
| `price_input_per_m` | DECIMAL(10,4) | NULL | 每百万输入 tokens 价格 |
| `price_output_per_m` | DECIMAL(10,4) | NULL | 每百万输出 tokens 价格 |
| `api_base_url` | TEXT | NULL | 旧字段，per-offering 的自定义 API |
| `price_updated_at` | DATETIME | NULL | — |
| `price_updated_by` | VARCHAR(100) | NULL | 历史遗留 label |
| `price_updated_by_admin_id` | BIGINT | NULL, **跨库无 FK** | 改价的 admin id |
| `provider_model_name` | VARCHAR(200) | NULL | provider 侧的模型实际名字 |
| `is_active`, `deleted_at` | — | — | 软删 |
| `created_by_admin_id`, `updated_by_admin_id` | BIGINT | NULL, **跨库无 FK** | 创建 / 修改者 |
| `created_at`, `updated_at` | — | — | Mixin |

约束：`UK (model_id, provider_id)`（同一模型在同一 provider 最多一条），索引齐备。

#### `provider_performance_metrics`

单次探测的原始性能指标（时序明细）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `offering_id` | BIGINT FK→model_provider_offerings.id | ON DELETE CASCADE, NOT NULL | — |
| `throughput_tps` | DECIMAL(8,2) | NULL | 每秒 tokens |
| `ttft_ms` | INT | NULL | 首 token 时间（ms） |
| `e2e_latency_ms` | INT | NULL | 端到端延时 |
| `success` | BOOL | NOT NULL | — |
| `error_code` | VARCHAR(50) | NULL | 失败分类 |
| `prompt_tokens`, `output_tokens` | INT | NULL | 用量 |
| `probe_region` | VARCHAR(50) | NULL | 探测区域 |
| `measured_at` | DATETIME | NOT NULL | 测量时间 |

索引：`idx_ppm_offering_time`、`idx_ppm_offering_region`、`idx_ppm_success_time`。**没有 TimestampMixin**（只有 `measured_at`）。

#### `provider_performance_daily_stats`

预聚合的每日指标（按 offering × region × date 唯一）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `offering_id` | BIGINT FK→model_provider_offerings.id | ON DELETE CASCADE | — |
| `probe_region` | VARCHAR(50) | NOT NULL | — |
| `stat_date` | DATE | NOT NULL | — |
| `sample_count`, `success_count`, `fail_count` | INT | NOT NULL | — |
| `avg_throughput_tps` | DECIMAL(10,2) | NULL | — |
| `avg_ttft_ms`, `avg_e2e_latency_ms` | INT | NULL | — |
| `min/max_throughput_tps` | DECIMAL(10,2) | NULL | — |
| `min/max_ttft_ms` | INT | NULL | — |
| `last_measured_at` | DATETIME | NULL | 当日最后一次采样 |
| `created_at`, `updated_at` | — | — | Mixin |

约束：`UK (offering_id, probe_region, stat_date)`；索引 `idx_ppds_date`、`idx_ppds_offering_date`。

#### `benchmark_jobs`

基准测试作业（队列消费者 arq 的一条任务）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `job_id` | VARCHAR(64) | UNIQUE, NOT NULL | 对外 job id |
| `job_type` | VARCHAR(16) | NOT NULL | `full` / `single` |
| `status` | VARCHAR(20) | DEFAULT 'queued' | `queued/running/succeeded/failed/partial` |
| `requested_by_admin_id` | BIGINT | NULL, **跨库无 FK** | 触发者 |
| `scope_offering_id` | BIGINT FK→model_provider_offerings.id | ON DELETE SET NULL, NULL | single 模式的目标 offering |
| `trigger_source` | VARCHAR(20) | DEFAULT 'manual' | `manual` / `scheduler` |
| `total/completed/succeeded/failed_offerings` | INT | DEFAULT 0 | 进度计数 |
| `queued_at`, `started_at`, `finished_at` | DATETIME | NULL | 时间点 |
| `error_message` | TEXT | NULL | 最后错误 |
| `created_at`, `updated_at` | — | — | Mixin |

索引：`idx_benchmark_jobs_status`、`_job_type`、`_requested_by`、`_scope_offering`、`_created_at`。

#### `admin_probe_audit_logs`

管理员手动发起的**单次**探测审计（与 `benchmark_jobs` 互补）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `job_id` | VARCHAR(64) | NOT NULL, 无 FK | 对应 `benchmark_jobs.job_id`（字符串引用） |
| `offering_id` | BIGINT FK→model_provider_offerings.id | ON DELETE SET NULL | — |
| `model_id` | BIGINT FK→models.id | ON DELETE SET NULL | — |
| `provider_id` | BIGINT FK→providers.id | ON DELETE SET NULL | — |
| `triggered_by_admin_id` | BIGINT | NULL, **跨库无 FK** | 触发者 |
| `status` | VARCHAR(20) | NOT NULL | `completed` / `failed` |
| `success` | BOOL | DEFAULT false | — |
| `error_code` | VARCHAR(128) | NULL | — |
| `ttft_ms`, `e2e_latency_ms`, `throughput_tps` | — | NULL | 指标 |
| `prompt_tokens`, `output_tokens` | INT | NULL | — |
| `probe_region` | VARCHAR(50) | NULL | — |
| `started_at`, `finished_at` | DATETIME | NULL | — |
| `created_at`, `updated_at` | — | — | Mixin |

索引：`idx_admin_probe_audits_job_id`、`_offering_id`、`_admin_id`、`_created_at`。

#### `provider_metrics_ranked`（VIEW）

**不是表，是视图**。ORM 里标注 `info: {"is_view": True}`。按 `(offering_id, probe_region, measured_at)` 排序打 `rn` 行号，供查询"最近 N 次探测"。视图定义在 Alembic migration 里维护。

---

## 6. 跨库引用总览

四个库之间**没有数据库层面的外键**。以下字段是靠应用层 / HMAC API 维护的"逻辑外键"：

| 引用方（库.表.字段） | 被引方（库.表.字段） | 语义 | 如何解析 |
|---|---|---|---|
| `admin.invitation_codes.used_by` | `user.users.uid` | 使用邀请码的用户 | user-service 注册时通过内部 API 通知 admin 消费 |
| `admin.admin_audit_logs.resource_id` | 任意（字符串） | 审计目标资源 ID | 自由字段，按 `resource_type` 语义解读 |
| `content.news.author_id` | `admin.admin_users.id` | 新闻作者 | content-service 显示作者名时通过 HMAC 调 admin 内部 API |
| `content.news.deleted_by_admin_id` | `admin.admin_users.id` | 软删操作者 | 同上 |
| `testing.provider_probe_configs.key_updated_by_admin_id` | `admin.admin_users.id` | 改 probe key 的管理员 | 审计展示用 |
| `testing.model_provider_offerings.price_updated_by_admin_id` | `admin.admin_users.id` | 改价的管理员 | 审计展示用 |
| `testing.model_provider_offerings.created_by_admin_id` | `admin.admin_users.id` | 创建者 | — |
| `testing.model_provider_offerings.updated_by_admin_id` | `admin.admin_users.id` | 修改者 | — |
| `testing.benchmark_jobs.requested_by_admin_id` | `admin.admin_users.id` | 触发 benchmark 的管理员 | testing-worker 通过 HMAC 调 admin `/api/v1/internal/admins/{uid}` |
| `testing.admin_probe_audit_logs.triggered_by_admin_id` | `admin.admin_users.id` | 手动探测触发者 | 同上 |

HMAC 调用链（参见 `docs/ARCHITECTURE.md` §3.2）：
- content → admin：展示新闻作者信息
- testing → admin：审计 / benchmark 展示触发者信息
- user → admin：消费/释放邀请码
- admin → user：获取用户总数

---

## 7. 迁移与快照

- **Alembic 是 schema 真理**：`migrations/<service>/versions/*.py`。`router` 目录已删除（新 router 无 DB）。
- `scripts/sql/*.sql` 是导出快照，**仅供应急 / phase2-cutover 工具参考**，不是权威。
- 建表 / 升级统一走：
  ```bash
  uv run migrate --service admin-service upgrade head
  uv run bootstrap-databases        # 一次 4 库全 upgrade
  ```

### 典型引用完整性约束摘要

| 模式 | 举例 |
|---|---|
| **CASCADE 删**（子随父消失） | `user_sessions.user_id → users.id`；`model_provider_offerings.model_id → models.id`；`provider_performance_metrics.offering_id → model_provider_offerings.id` |
| **SET NULL**（保留残影） | 所有自引用 `admin_users.{created_by,updated_by,...}_admin_id`；`invitation_codes.created_by`；`benchmark_jobs.scope_offering_id`；`admin_probe_audit_logs.{offering,model,provider}_id` |
| **RESTRICT**（拦住硬删） | `admin_audit_logs.actor_admin_id → admin_users.id` |
| **无 FK（跨库）** | §6 的所有条目 |

---

## 8. 速查

**哪些表有软删？**
- `content.news`（`deleted_at`）
- `testing.model_vendors` / `testing.providers` / `testing.model_provider_offerings`（`deleted_at`）
- 其他表是硬状态（`status=0`/`is_active=false`）或直接物理删除

**哪些表用自增而非雪花 ID？**
- `admin.admin_audit_logs`
- `user.email_verification_codes`
- `testing.model_categories` / `model_vendors` / `models` / `providers` / `model_provider_offerings` / `provider_performance_metrics` / `provider_performance_daily_stats` / `benchmark_jobs` / `admin_probe_audit_logs` / `provider_probe_configs`
- 其余都是 Snowflake（`common/db/base.py::SnowflakeIdMixin`）

**哪些是多对多连接表？**
- `testing.model_category_map`（models × model_categories）

**哪些字段将来迁 PostgreSQL 需要审查？**
- `users.email`：lowercase/trim 约定固化（Postgres 默认区分大小写）
- `models.capability_tags`：JSON → JSONB + GIN
- 所有 `DateTime`：naive → `TIMESTAMPTZ`（`migrations/README.md` 专段记录）
