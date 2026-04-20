# User Service Remaining Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 `user_service` 在不改 `router-service` 前提下可自闭环的剩余重构，并将数据库实例迁移到最新 revision。

**Architecture:** 继续沿用当前 `endpoint -> service -> model` 分层，在 `src/user_service` 内新增 billing/key/admin/worker 模块。用户端暴露 `/api/v1/billing/*` 与 `/api/v1/keys/*`，管理员端暴露不与现有 admin-service 冲突的 `/api/v1/admin/...` 子路径；异步任务复用现有 ARQ worker 模式。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, Alembic, Pydantic v2, ARQ, MySQL

---

## File Map

- Create: `src/user_service/services/balance_service.py`
- Create: `src/user_service/services/api_key_service.py`
- Create: `src/user_service/services/topup_order_service.py`
- Create: `src/user_service/services/usage_stat_service.py`
- Create: `src/user_service/api/v1/endpoints/billing.py`
- Create: `src/user_service/api/v1/endpoints/keys.py`
- Create: `src/user_service/api/v1/endpoints/admin_billing.py`
- Create: `src/user_service/worker.py`
- Create: `src/user_service/jobs.py`
- Modify: `src/user_service/schemas.py`
- Modify: `src/user_service/services/__init__.py`
- Modify: `src/user_service/api/v1/endpoints/__init__.py`
- Modify: `src/user_service/api/v1/router.py`
- Modify: `src/backend_app/main.py`
- Modify: `src/user_service/config.py`
- Test: `tests/test_user_rebuild.py`
- Test: `tests/test_backend_app.py`

### Task 1: Billing / Key Service Layer

**Files:**
- Create: `src/user_service/services/balance_service.py`
- Create: `src/user_service/services/api_key_service.py`
- Create: `src/user_service/services/topup_order_service.py`
- Create: `src/user_service/services/usage_stat_service.py`
- Modify: `src/user_service/services/__init__.py`
- Modify: `src/user_service/models/*.py`
- Test: `tests/test_user_rebuild.py`

- [x] **Step 1: 写 service 层红灯测试**
- [x] **Step 2: 运行定向测试确认失败**
- [x] **Step 3: 实现 `BalanceService`**
- [x] **Step 4: 实现 `ApiKeyService`**
- [x] **Step 5: 实现 `TopupOrderService` 与 `UsageStatService`**
- [x] **Step 6: 运行定向测试确认转绿**

### Task 2: 用户端 Billing / Keys API

**Files:**
- Create: `src/user_service/api/v1/endpoints/billing.py`
- Create: `src/user_service/api/v1/endpoints/keys.py`
- Modify: `src/user_service/schemas.py`
- Modify: `src/user_service/api/v1/endpoints/__init__.py`
- Modify: `src/user_service/api/v1/router.py`
- Modify: `src/backend_app/main.py`
- Test: `tests/test_user_rebuild.py`
- Test: `tests/test_backend_app.py`

- [x] **Step 1: 写 `/billing/*` 与 `/keys/*` 红灯测试**
- [x] **Step 2: 运行定向测试确认失败**
- [x] **Step 3: 新增响应 schema 与 endpoint**
- [x] **Step 4: 挂载到 merged backend**
- [x] **Step 5: 运行定向测试确认转绿**

### Task 3: 管理员端 Billing API 与 Worker

**Files:**
- Create: `src/user_service/api/v1/endpoints/admin_billing.py`
- Create: `src/user_service/jobs.py`
- Create: `src/user_service/worker.py`
- Modify: `src/user_service/config.py`
- Modify: `src/user_service/api/v1/endpoints/__init__.py`
- Modify: `src/user_service/api/v1/router.py`
- Modify: `src/backend_app/main.py`
- Test: `tests/test_user_rebuild.py`
- Test: `tests/test_backend_app.py`

- [x] **Step 1: 写管理员端和 worker 红灯测试**
- [x] **Step 2: 运行定向测试确认失败**
- [x] **Step 3: 新增管理员端 topup / adjust / list API**
- [x] **Step 4: 新增 invitation outbox / usage aggregate / verification cleanup 任务**
- [x] **Step 5: 运行定向测试确认转绿**

### Task 4: 数据库迁移与回归验证

**Files:**
- Modify: `bug_fix/user-service/2026-04-20-audit-fixes.md`
- Modify: `bug_fix/user-service/2026-04-20-full-rebuild-plan.md`
- Run: `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py tests/test_user_rebuild.py tests/test_backend_app.py tests/test_schema_ownership.py tests/test_architecture_boundaries.py -v`
- Run: `uv run migrate --service user-service upgrade head`

- [x] **Step 1: 跑完整 user-service 回归测试**
- [x] **Step 2: 实际执行 user-service Alembic upgrade**
- [x] **Step 3: 回填文档中的实施结果和 migration 状态**

## Implementation Result

- 状态：`done`
- 修复补充：`migrations/_env_shared.py` 在 async online migration 路径中已于 `run_sync(do_run_migrations)` 成功后显式 `await connection.commit()`。
- 根因：MySQL DDL 会自动提交，但 Alembic 版本表的 `UPDATE alembic_version ...` 仍处于 SQLAlchemy async connection 的隐式事务中；连接退出时 rollback，导致外键 DDL 已落库但 revision 停在 `20260420_08_create_invitation_release_outbox`。
- 当前数据库状态：`user-service` 已升级到 `20260420_10_billing_idempotency_constraints (head)`。
- 验证：
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_migration_structure.py -k shared_async_migration_env_commits_version_table_updates -v`
  - `timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service user-service upgrade head`
  - `timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service user-service current --verbose`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py tests/test_user_rebuild.py tests/test_backend_app.py tests/test_schema_ownership.py tests/test_schema_drift.py tests/test_architecture_boundaries.py tests/test_migration_structure.py -v`
- 认证审阅补充：
  - 打通 `/auth/send-email-code` 的 `verify` purpose，供 `/auth/verify-email` 使用
  - 改密/重置密码的 session revoke 与密码变更同事务提交
  - 禁用用户禁止 reset-password，pending 用户在登录态依赖层被拒绝
  - 验证码登录成功会重置密码登录失败计数和锁定状态
- billing 审阅补充：
  - 账务 mutation 读取用户/订单/API key 行时使用 `SELECT ... FOR UPDATE`
  - `balance_transactions(type, ref_type, ref_id)` 增加唯一键，业务写入先做幂等检查
  - 充值订单只允许 `PENDING` 状态入账，避免重复充值
  - 用户端账务 schema 移除内部用户 ID、管理员 ID、IP，管理员端改用专用 schema
  - `/billing/balance` 返回 `frozen_amount` 与 `available_balance`
  - 用户端 usage/stats 与 usage/logs 默认最近 30 天，最大跨度 90 天
  - `usage_stats` 新增 `account_api_key_id` 与 `uk_usage_stats_bucket_effective`，修复 MySQL NULL 唯一键问题
- 最终结果：`68 passed, 1 skipped, 3 warnings`
