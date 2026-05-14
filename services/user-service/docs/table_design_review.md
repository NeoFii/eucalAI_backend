# User-Service 数据表设计审查报告

**审查日期**: 2026-05-14  
**审查范围**: `eucal_ai_user` 数据库全部 9 张业务表  
**审查人**: AI Assistant

---

## 总体评价

设计质量良好，核心决策正确：

- Snowflake ID 主键，天然支持分布式扩展
- 微元精度（1 CNY = 1,000,000）避免浮点误差
- `balance_transactions` append-only 账本设计，余额可审计可追溯
- 敏感数据 hash-only 存储（API Key、验证码、Voucher Code）
- 索引设计覆盖主要查询路径，联合索引方向合理（低基数列在前 + 时间列在后）

以下为发现的问题及改进建议。

---

## 问题清单

### P0 — 高优先级

#### 1. `api_call_logs.updated_at` 缺少自动更新

**现状**:

```sql
`updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Updated at'
```

没有 `ON UPDATE CURRENT_TIMESTAMP`，而 `users` 表是有的。

**影响**: Worker 回填 status/cost 等字段时，如果通过原生 SQL 或批量 UPDATE 操作，`updated_at` 不会自动刷新，导致审计时间线断裂。

**修复**:

```sql
ALTER TABLE api_call_logs
  MODIFY COLUMN updated_at datetime NOT NULL
  DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
  COMMENT 'Updated at';
```

---

#### 2. `balance_transactions` 幂等约束对 NULL 失效

**现状**:

```sql
UNIQUE KEY `uk_balance_tx_type_ref` (`type`, `ref_type`, `ref_id`)
```

**影响**: MySQL UNIQUE 约束中，NULL != NULL。当 `ref_type` 和 `ref_id` 为 NULL 时（如部分 ADMIN_ADJUST 场景），同一笔操作可被重复插入，破坏幂等性。

**修复方案（二选一）**:

- 方案 A：业务层保证 ADMIN_ADJUST 必须填写 `ref_type="admin_adjust"` + `ref_id="{操作唯一标识}"`
- 方案 B：将 NULL 替换为 sentinel 值（如 `ref_type` 默认 `"_"`，`ref_id` 默认 `"_"`），使约束生效

推荐方案 A，从业务入口堵住，不引入 magic value。

---

### P1 — 中优先级

#### 3. `api_call_logs` 缺少 `provider_slug` 索引

**现状**: 已有 user、key、model、status、tier 五个维度的联合索引，但没有 provider 维度。

**影响**: 按供应商排查故障（如 "最近 1 小时某 provider 错误率飙升"）需要全表扫描。当前 ~1000 行无感知，数据量到 100 万+ 后会成为瓶颈。

**修复**:

```sql
ALTER TABLE api_call_logs
  ADD INDEX idx_api_call_logs_provider_created (provider_slug, created_at);
```

---

#### 4. `user_sessions` 缺少过期清理索引

**现状**: 无 `expires_at` 索引。

**影响**: 定期清理过期 session（`DELETE WHERE expires_at < NOW() AND revoked_at IS NULL`）随数据增长退化为全表扫描。

**修复**:

```sql
ALTER TABLE user_sessions
  ADD INDEX idx_user_sessions_expires_at (expires_at);
```

---

#### 5. `voucher_redemption_codes.redeemed_user` 关系加载策略不当

**现状**: ORM 模型中 `lazy="selectin"`，每次查询 voucher 自动加载关联 User。

**影响**: 管理后台分页列表查询时产生不必要的 JOIN/子查询，放大数据库负载。

**修复**: 改为 `lazy="noload"` 或 `lazy="raise"`，需要时通过 `options=[selectinload(VoucherRedemptionCode.redeemed_user)]` 显式加载。

```python
redeemed_user = relationship("User", lazy="noload")
```

---

### P2 — 低优先级

#### 6. `api_call_logs.total_tokens` 语义歧义

**现状**: 注释为 `prompt+completion+cached`。

**问题**: `cached_tokens` 通常是 `prompt_tokens` 的子集（缓存命中的 prompt 部分），不应额外累加。实际语义应为：

- `total_tokens = prompt_tokens + completion_tokens`
- `cached_tokens` 是 prompt_tokens 中命中缓存的部分（用于计费折扣）

**修复**: 更正注释为 `prompt_tokens + completion_tokens`，确认代码中计算逻辑一致。

---

#### 7. `usage_stats` 双 UNIQUE 约束冗余

**现状**:

```sql
UNIQUE KEY `uk_usage_stats_bucket` (`user_id`, `api_key_id`, `model_name`, `stat_hour`)
UNIQUE KEY `uk_usage_stats_bucket_effective` (`user_id`, `account_api_key_id`, `model_name`, `stat_hour`)
```

**问题**: `account_api_key_id` 列的存在就是为了解决 `api_key_id` 为 NULL 时唯一约束失效的问题。既然 `_effective` 约束已经覆盖了所有场景，原始的 `uk_usage_stats_bucket` 就是冗余的（NULL 本来就不会冲突，所以它也不会真正防重）。

**修复**: 删除冗余约束，减少写入时的索引维护开销。

```sql
ALTER TABLE usage_stats DROP INDEX uk_usage_stats_bucket;
```

---

#### 8. `users` 表金额字段缺少 DDL COMMENT

**现状**: `balance`、`frozen_amount`、`used_amount` 在 DDL 中没有 COMMENT。ORM 模型有中文注释但未传递到数据库。

**修复**:

```sql
ALTER TABLE users
  MODIFY COLUMN balance bigint NOT NULL DEFAULT 0 COMMENT '可用余额（微元，¥1=1000000）',
  MODIFY COLUMN frozen_amount bigint NOT NULL DEFAULT 0 COMMENT '预冻结中的余额（微元）',
  MODIFY COLUMN used_amount bigint NOT NULL DEFAULT 0 COMMENT '历史累计消费（微元）';
```

---

#### 9. `email_verification_codes` 未使用 Snowflake ID

**现状**: 使用 `BigInteger autoincrement` 主键，其余所有表统一使用 SnowflakeIdMixin。

**影响**: 功能无碍，但风格不一致。若未来分库分表，自增 ID 会成为障碍。

**修复**: 下次迁移时统一为 Snowflake ID，或标注为已知技术债。

---

## 汇总

| 优先级 | 编号 | 表 | 问题 |
|--------|------|----|------|
| P0 | 1 | api_call_logs | updated_at 缺 ON UPDATE |
| P0 | 2 | balance_transactions | 幂等约束 NULL 漏洞 |
| P1 | 3 | api_call_logs | 缺 provider_slug 索引 |
| P1 | 4 | user_sessions | 缺 expires_at 索引 |
| P1 | 5 | voucher_redemption_codes | selectin 加载策略 |
| P2 | 6 | api_call_logs | total_tokens 注释语义 |
| P2 | 7 | usage_stats | 冗余 UNIQUE 约束 |
| P2 | 8 | users | 金额字段缺 COMMENT |
| P2 | 9 | email_verification_codes | 未用 Snowflake ID |

---

## 附录：表结构概览

| 表名 | 行数 | 数据大小 | 用途 |
|------|------|----------|------|
| users | 2 | 16 KB | 用户主表 |
| user_api_keys | 11 | 16 KB | 用户 API Key |
| user_sessions | 34 | 16 KB | Refresh Token 会话 |
| api_call_logs | 1,014 | 32 MB | 请求审计日志 |
| balance_transactions | 457 | 80 KB | 余额流水账本 |
| topup_orders | 12 | 16 KB | 充值订单 |
| usage_stats | 60 | 16 KB | 小时级用量聚合 |
| email_verification_codes | 2 | 16 KB | 邮箱验证码 |
| voucher_redemption_codes | 7 | 16 KB | 兑换码 |
