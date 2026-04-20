# Schema Ownership

> 每个 MySQL schema 归哪个服务所有，对应的 Alembic 迁移目录、SQL 快照、和拥有的表一览。

## 所有权汇总

| Service | Alembic | Schema snapshot | Database env |
|---|---|---|---|
| admin-service | `migrations/admin_service` | `scripts/sql/admin_schema.sql` | `ADMIN_DATABASE_URL` |
| user-service | `migrations/user_service` | `scripts/sql/user_schema.sql` | `USER_DATABASE_URL` |
| testing-service | `migrations/testing_service` | `scripts/sql/testing_schema.sql` | `TESTING_DATABASE_URL` |

`router-service` 是纯 ML 推理服务，**无数据库**：配额、API key、调用日志、用量统计都落在 `user-service` 库，router 通过 HMAC 内部接口读写。

`scripts/sql/init_tables.sql` 是一键拉起所有 schema 的聚合入口（执行顺序：admin → user → testing）。

## 各服务拥有的表 / 视图

### admin-service
- `admin_users`
- `admin_audit_logs`
- `invitation_codes`

### user-service
- `users`
- `user_sessions`
- `email_verification_codes`
- `user_api_keys`
- `balance_transactions`
- `topup_orders`
- `api_call_logs`（由 router-service 通过 HMAC 写入）
- `usage_stats`（由 user-service arq worker 写入）
- `invitation_release_outbox`（注册失败补偿队列）

### testing-service
- `model_categories`
- `model_vendors`
- `models`
- `model_category_map`
- `providers`
- `provider_probe_configs`
- `model_provider_offerings`
- `provider_performance_metrics`
- `provider_performance_daily_stats`
- `benchmark_jobs`
- `admin_probe_audit_logs`
- VIEW `provider_metrics_ranked`

## 常用操作

```bash
# 一键初始化所有数据库（按顺序执行每个服务的 Alembic upgrade head）
uv run bootstrap-databases

# 单服务 Alembic
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service revision -m "..." --autogenerate

# 查看 schema 快照（不是真理，见 migrations/README.md）
cat scripts/sql/admin_schema.sql
cat scripts/sql/user_schema.sql
cat scripts/sql/testing_schema.sql
```

## 跨服务引用

跨服务字段引用（例如 `api_call_logs.api_key_id` → `user_service.user_api_keys.id`，`balance_transactions.operator_id` → `admin_service.admin_users.uid`）只保存外键值，不在数据库层建 FK；一致性由应用层 HMAC 调用维护。详见 `migrations/cutover_manifest.json::external_reference_columns`。
