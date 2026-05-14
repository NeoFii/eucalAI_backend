# Admin-Service 数据库表结构文档

> 生成时间：2026-05-14  
> 数据库：MySQL (InnoDB)  
> 时区：Asia/Shanghai（naive datetime，应用层统一 +08:00）  
> 主键策略：Snowflake ID（BigInteger），对外暴露 NanoID UID

---

## 枚举定义

| 枚举类型 | 值 | 含义 |
|---------|---|------|
| AdminRole | 0 | admin（普通管理员） |
| AdminRole | 1 | super_admin（超级管理员） |
| AdminStatus | 0 | disabled（已禁用） |
| AdminStatus | 1 | active（正常） |
| PoolAccountStatus | 0 | active（正常可用） |
| PoolAccountStatus | 1 | disabled（手动禁用） |
| PoolAccountStatus | 2 | exhausted（余额耗尽） |
| PoolAccountStatus | 3 | error（健康检查异常） |

---

## 1. admin_users — 管理员账户

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| uid | VARCHAR(20) | NO | — | 对外暴露的 NanoID |
| email | VARCHAR(255) | NO | — | 登录邮箱 |
| password_hash | VARCHAR(255) | NO | — | 密码哈希（bcrypt） |
| name | VARCHAR(100) | NO | — | 显示名称 |
| status | SMALLINT | NO | 1 | 0=disabled 1=active |
| role | SMALLINT | NO | 0 | 0=admin 1=super_admin |
| is_root | BOOLEAN | NO | 0 | 根管理员标记，仅 bootstrap 创建的超管为 true |
| created_by_admin_id | BIGINT | YES | NULL | 创建者 admin id |
| updated_by_admin_id | BIGINT | YES | NULL | 最后修改者 admin id |
| password_changed_at | DATETIME | YES | NULL | 最后密码修改时间 |
| password_changed_by_admin_id | BIGINT | YES | NULL | 最后密码修改者 admin id |
| last_login_at | DATETIME | YES | NULL | 最后登录时间 |
| last_login_ip | VARCHAR(45) | YES | NULL | 最后登录 IP |
| login_fail_count | INT | NO | 0 | 连续登录失败次数 |
| login_locked_until | DATETIME | YES | NULL | 登录锁定到期时间 |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间（自动） |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| (unique) | uid | 唯一 |
| (unique) | email | 唯一 |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| created_by_admin_id | admin_users.id | SET NULL |
| updated_by_admin_id | admin_users.id | SET NULL |
| password_changed_by_admin_id | admin_users.id | SET NULL |

**CHECK 约束：**
| 约束名 | 表达式 |
|--------|--------|
| chk_admin_users_role | role IN (0, 1) |
| chk_admin_users_status | status IN (0, 1) |

---

## 2. audit_action_definitions — 审计操作码注册表

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| code | VARCHAR(100) | NO | — | 操作码（主键，如 create_admin） |
| label | VARCHAR(120) | NO | — | 中文显示名 |
| category | VARCHAR(32) | NO | — | 分类分组（governance/auth/user_management/model_catalog/routing_config/voucher/pool） |
| resource_type | VARCHAR(50) | NO | — | 关联资源类型（admin_user/user/model_vendor 等） |
| description | VARCHAR(255) | YES | NULL | 可选详细说明 |
| is_active | BOOLEAN | NO | true | 是否允许新日志使用此 code |
| sort_order | INT | NO | 0 | 前端展示排序 |
| created_at | DATETIME | NO | now() | 创建时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | code | 主键（自然键） |

---

## 3. admin_audit_logs — 管理员操作审计日志

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | AUTO_INCREMENT | 主键 |
| actor_admin_id | BIGINT | NO | — | 操作者 admin id |
| target_admin_id | BIGINT | YES | NULL | 操作目标 admin id |
| action | VARCHAR(100) | NO | — | 操作码（FK → audit_action_definitions.code） |
| resource_type | VARCHAR(50) | NO | — | 资源类型（冗余，方便直接过滤） |
| resource_id | VARCHAR(100) | YES | NULL | 资源标识 |
| status | VARCHAR(20) | NO | — | success / failed |
| before_data | JSON | YES | NULL | 变更前数据快照 |
| after_data | JSON | YES | NULL | 变更后数据快照 |
| reason | VARCHAR(255) | YES | NULL | 原因或失败摘要 |
| ip_address | VARCHAR(45) | YES | NULL | 来源 IP |
| user_agent | VARCHAR(512) | YES | NULL | 来源 User-Agent |
| created_at | DATETIME | NO | now() | 事件时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| ix_admin_audit_logs_actor | actor_admin_id | 普通 |
| ix_admin_audit_logs_target | target_admin_id | 普通 |
| ix_admin_audit_logs_action | action | 普通 |
| ix_admin_audit_logs_resource_type | resource_type | 普通 |
| ix_admin_audit_logs_created_at | created_at | 普通 |

**外键：**
| 列 | 引用 | ON DELETE | ON UPDATE |
|---|------|----------|-----------|
| actor_admin_id | admin_users.id | RESTRICT | — |
| target_admin_id | admin_users.id | SET NULL | — |
| action | audit_action_definitions.code | RESTRICT | CASCADE |

---

## 4. model_vendors — 模型研发商

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| slug | VARCHAR(80) | NO | — | 研发商标识 |
| name | VARCHAR(120) | NO | — | 显示名称 |
| logo_url | VARCHAR(512) | YES | NULL | Logo URL |
| is_active | BOOLEAN | NO | true | 是否启用 |
| sort_order | INT | NO | 0 | 排序权重 |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| (unique) | slug | 唯一 |

---

## 5. model_categories — 模型能力分类

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| key | VARCHAR(80) | NO | — | 分类标识 |
| name | VARCHAR(120) | NO | — | 显示名称 |
| sort_order | INT | NO | 0 | 排序权重 |
| is_active | BOOLEAN | NO | true | 是否启用 |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| (unique) | key | 唯一 |

---

## 6. supported_models — 支持的模型目录

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| slug | VARCHAR(120) | NO | — | 模型标识（面向用户） |
| routing_slug | VARCHAR(200) | YES | NULL | 路由用 slug，对应 pool_models.model_slug |
| name | VARCHAR(160) | NO | — | 模型显示名称 |
| vendor_id | BIGINT | NO | — | 研发商 id（FK） |
| summary | VARCHAR(255) | YES | NULL | 模型卡片摘要 |
| description | TEXT | YES | NULL | 模型详细描述 |
| input_price_per_million | BIGINT | YES | NULL | 每百万输入 token 价格（微元） |
| output_price_per_million | BIGINT | YES | NULL | 每百万输出 token 价格（微元） |
| cached_input_price_per_million | BIGINT | YES | NULL | 缓存命中输入价格（微元） |
| capability_tags | JSON | NO | [] | 能力标签列表 |
| context_window | INT | YES | NULL | 上下文窗口 token 数 |
| max_output_tokens | INT | YES | NULL | 最大输出 token 数 |
| is_reasoning_model | BOOLEAN | NO | false | 是否为推理模型 |
| is_active | BOOLEAN | NO | true | 是否在线（false=归档） |
| sort_order | INT | NO | 0 | 排序权重 |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| (unique) | slug | 唯一 |
| (unique) | routing_slug | 唯一 |
| ix_supported_models_vendor_id | vendor_id | 普通 |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| vendor_id | model_vendors.id | RESTRICT |

**CHECK 约束：**
| 约束名 | 表达式 |
|--------|--------|
| chk_active_needs_routing_slug | is_active = 0 OR routing_slug IS NOT NULL |
| chk_active_needs_pricing | is_active = 0 OR (input_price_per_million IS NOT NULL AND output_price_per_million IS NOT NULL) |

---

## 7. supported_model_category_map — 模型-分类多对多映射

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| model_id | BIGINT | NO | — | 模型 id |
| category_id | BIGINT | NO | — | 分类 id |
| sort_order | INT | NO | 0 | 模型内分类排序 |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| uk_supported_model_category | (model_id, category_id) | 唯一 |
| ix_model_id | model_id | 普通 |
| ix_category_id | category_id | 普通 |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| model_id | supported_models.id | CASCADE |
| category_id | model_categories.id | CASCADE |

---

## 8. pools — 资源池

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| slug | VARCHAR(64) | NO | — | 引用标识 |
| name | VARCHAR(128) | NO | — | 显示名称 |
| base_url | VARCHAR(512) | NO | — | 平台统一请求地址 |
| is_enabled | BOOLEAN | NO | true | 是否启用 |
| priority | INT | NO | 0 | 路由优先级，越大越优先 |
| weight | INT | NO | 1 | 路由权重 |
| health_check_endpoint | VARCHAR(512) | YES | NULL | 余额/状态检查接口 |
| remark | VARCHAR(256) | YES | NULL | 备注 |
| created_by | BIGINT | YES | NULL | 创建者 admin id |
| updated_by | BIGINT | YES | NULL | 最后修改者 admin id |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| (unique) | slug | 唯一 |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| created_by | admin_users.id | SET NULL |
| updated_by | admin_users.id | SET NULL |

---

## 9. pool_models — 资源池模型配置

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| pool_id | BIGINT | NO | — | 所属资源池 |
| model_slug | VARCHAR(120) | NO | — | 系统模型标识 |
| upstream_model_id | VARCHAR(200) | NO | — | 上游实际模型 ID |
| input_price_per_million | BIGINT | NO | 0 | 每百万输入 token 价格（微元） |
| output_price_per_million | BIGINT | NO | 0 | 每百万输出 token 价格（微元） |
| cached_input_price_per_million | BIGINT | YES | NULL | 缓存命中输入价格（微元） |
| context_length | INT | YES | NULL | 该平台对此模型的最大上下文长度 |
| is_enabled | BOOLEAN | NO | true | 是否启用 |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| uq_pool_model | (pool_id, model_slug) | 唯一 |
| ix_pool_models_routing | (pool_id, is_enabled, model_slug) | 复合 |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| pool_id | pools.id | CASCADE |

---

## 10. pool_accounts — 资源池账号

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | NO | Snowflake | 内部主键 |
| pool_id | BIGINT | NO | — | 所属资源池 |
| name | VARCHAR(128) | NO | — | 备注名 |
| api_key_enc | JSON | NO | — | AES-256-GCM 加密 {ciphertext, iv, tag} |
| mask | VARCHAR(32) | NO | — | 脱敏显示（如 sk-...xxxx） |
| balance | BIGINT | NO | 0 | 余额（微元） |
| status | SMALLINT | NO | 0 | 0=active 1=disabled 2=exhausted 3=error |
| rpm_limit | INT | YES | NULL | 每分钟请求上限 |
| tpm_limit | INT | YES | NULL | 每分钟 token 上限 |
| weight | INT | NO | 1 | 轮转权重 |
| last_checked_at | DATETIME | YES | NULL | 上次健康检查时间 |
| last_health_check_error | VARCHAR(512) | YES | NULL | 上次健康检查错误信息 |
| remark | VARCHAR(256) | YES | NULL | 备注 |
| created_by | BIGINT | YES | NULL | 创建者 admin id |
| updated_by | BIGINT | YES | NULL | 最后修改者 admin id |
| created_at | DATETIME | NO | now() | 创建时间 |
| updated_at | DATETIME | NO | now() | 更新时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | id | 主键 |
| ix_pool_accounts_routing | (pool_id, status) | 复合 |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| pool_id | pools.id | CASCADE |
| created_by | admin_users.id | SET NULL |
| updated_by | admin_users.id | SET NULL |

**CHECK 约束：**
| 约束名 | 表达式 |
|--------|--------|
| chk_pool_accounts_status | status IN (0, 1, 2, 3) |

---

## 11. routing_settings — 路由策略配置（KV 表）

| 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| key | VARCHAR(64) | NO | — | 配置键（主键） |
| value | TEXT | NO | — | 配置值 |
| value_type | VARCHAR(16) | NO | 'string' | 值类型：string/float/int |
| group_name | VARCHAR(32) | NO | — | 分组：general/weights/score_bands/tier_model_map |
| label | VARCHAR(128) | NO | — | 管理端显示名 |
| description | VARCHAR(512) | YES | NULL | 配置说明 |
| sort_order | INT | NO | 0 | 组内排序 |
| updated_by | BIGINT | YES | NULL | 最后修改者 admin id |
| updated_at | DATETIME | NO | now() | 更新时间 |
| created_at | DATETIME | NO | now() | 创建时间 |

**索引：**
| 索引名 | 列 | 类型 |
|--------|---|------|
| PRIMARY | key | 主键（自然键） |

**外键：**
| 列 | 引用 | ON DELETE |
|---|------|----------|
| updated_by | admin_users.id | SET NULL |

---

## 外键关系总览

```
audit_action_definitions
    └── admin_audit_logs.action (RESTRICT / CASCADE on UPDATE)

admin_users (self-ref: created_by, updated_by, password_changed_by)
    ├── admin_audit_logs.actor_admin_id (RESTRICT)
    ├── admin_audit_logs.target_admin_id (SET NULL)
    ├── pools.created_by (SET NULL)
    ├── pools.updated_by (SET NULL)
    ├── pool_accounts.created_by (SET NULL)
    ├── pool_accounts.updated_by (SET NULL)
    └── routing_settings.updated_by (SET NULL)

pools
    ├── pool_models.pool_id (CASCADE)
    └── pool_accounts.pool_id (CASCADE)

model_vendors
    └── supported_models.vendor_id (RESTRICT)

model_categories
    └── supported_model_category_map.category_id (CASCADE)

supported_models
    └── supported_model_category_map.model_id (CASCADE)
```

---

## 公共 Mixin 说明

| Mixin | 提供的列 |
|-------|---------|
| SnowflakeIdMixin | `id BIGINT PRIMARY KEY` (Snowflake 生成) |
| TimestampMixin | `created_at DATETIME NOT NULL`, `updated_at DATETIME NOT NULL` (自动维护) |

---

## 价格存储约定

所有价格字段使用 **BIGINT 微元**（1 元 = 1,000,000 微元），避免浮点精度问题。字段命名统一为 `*_price_per_million`，表示每百万 token 的价格（微元）。

---

## 表清单（共 11 张）

| # | 表名 | 主键类型 | 说明 |
|---|------|---------|------|
| 1 | admin_users | Snowflake | 管理员账户 |
| 2 | audit_action_definitions | 自然键 (code) | 审计操作码注册表 |
| 3 | admin_audit_logs | AUTO_INCREMENT | 管理员操作审计日志 |
| 4 | model_vendors | Snowflake | 模型研发商 |
| 5 | model_categories | Snowflake | 模型能力分类 |
| 6 | supported_models | Snowflake | 支持的模型目录 |
| 7 | supported_model_category_map | Snowflake | 模型-分类多对多映射 |
| 8 | pools | Snowflake | 资源池 |
| 9 | pool_models | Snowflake | 资源池模型配置 |
| 10 | pool_accounts | Snowflake | 资源池账号 |
| 11 | routing_settings | 自然键 (key) | 路由策略配置 KV 表 |
