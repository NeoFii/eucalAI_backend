# User Service Audit Fix Plan

> 范围：仅针对 `src/user_service` 当前已存在结构和代码设计审计出的缺陷进行修复。
> 原则：按风险优先级修复，所有行为变更先补回归测试，再改实现，再补验证结果。

## 修复目标

- 修复当前认证链路中的高风险安全与一致性问题
- 收敛 service 层事务边界，避免半成功状态
- 修复输入校验、邮件验证码、邮箱规范化等行为偏差
- 为每项修复记录根因、改动点和验证命令

## 优先级

### P0

- [x] 禁用用户可通过 `/auth/send-email-code` + `/auth/verify-email` 重新激活
- [x] `/auth/send-email-code` 无条件返回成功，且 SMTP 失败时仍替换旧验证码
- [x] `AuthService` 事务边界切碎，登录/改密/重置密码存在半成功状态
- [x] 改密/重置密码后旧 refresh session 撤销未随同事务持久化
- [x] 用户账务写路径缺少行锁和业务幂等约束
- [x] 同一充值订单可重复入账

### P1

- [x] 注册补偿仅覆盖 `release_invitation_code()` 抛异常，未覆盖返回 `False`
- [x] 验证码在注册/验证邮箱/验证码登录/重置密码中消费过早
- [x] `/auth/verify-email` 需要 `verify` 验证码，但发送验证码 schema 不允许 `verify`
- [x] 禁用用户仍可通过 reset-password 修改密码
- [x] 用户账务响应暴露内部主键/管理员 ID，余额响应缺少冻结金额

### P2

- [x] `lang` 在 schema validator 中基本不生效
- [x] 邮箱 lowercase/trim 规范只写在注释里，没有真正执行
- [x] 注册后的自动登录缺失 `user_agent` / `ip_address` 审计信息
- [x] 账本/日志扩展表缺少本地外键约束
- [x] user-service 迁移执行后 DDL 已落库但 `alembic_version` 未推进到 head
- [x] pending 用户未在登录态依赖层防御性拦截
- [x] 验证码登录成功后未清理密码登录失败计数/锁定状态
- [x] usage/logs 默认无时间窗口且 usage_stats account bucket 唯一约束在 MySQL NULL 语义下不可靠

## 执行顺序

1. 先补 P0 回归测试并确认红灯
2. 逐项实现 P0 最小修复并跑定向测试
3. 再进入 P1，优先修复补偿和验证码消费时机
4. 最后处理 P2 的输入规范化和审计字段问题
5. 跑 user-service 相关测试并回填本文档

## 修复记录

### P0.1 禁用用户重新激活漏洞

- 状态：`done`
- 根因：`send-email-code` 接口允许任意 `purpose`，`verify_email()` 会直接把用户状态改成 `1`
- 实际修复：
  - `SendEmailCodeRequest.purpose` 改为受控枚举：`register | reset_password | login | verify`
  - `AuthService.verify_email()` 对 `status=0` 直接抛 `UserDisabledException`
  - 对 `status=2` 才恢复为 `active`

### P0.2 发送验证码假成功

- 状态：`done`
- 根因：endpoint 丢弃 `send_verification_code()` 的失败返回；service 先删除旧码再提交，即使邮件发送失败也会落库
- 实际修复：
  - endpoint 遇到 `(False, message)` 会抛出 `ServiceUnavailableException`
  - `EmailService.send_verification_code()` 改为仅在 `_send_email()` 成功后才删除旧码并持久化新码

### P0.3 会话和密码事务半成功

- 状态：`done`
- 根因：`_revoke_all_user_sessions()` 内部自行 `commit()`，导致登录/改密/重置密码跨多个事务
- 实际修复：
  - `_revoke_all_user_sessions()` 只做内存态修改，不再内部提交
  - 登录、改密、验证码登录、重置密码改为由上层统一提交

### P0.4 改密/重置后旧 refresh session 仍有效

- 状态：`done`
- 根因：`change_password()` 与 `reset_password()` 先提交密码变更，再调用 `_revoke_all_user_sessions()`，撤销标记没有后续 commit
- 实际修复：
  - `change_password()` 改为先写 password hash，再撤销所有未撤销 session，最后一次性 commit
  - `reset_password()` 改为先写 password hash 与验证码 used_at，再撤销所有未撤销 session，最后一次性 commit
  - 新增回归测试断言 commit 发生时 session 已经带有 `revoked_at`

### P0.5 用户账务写路径并发与幂等缺失

- 状态：`done`
- 根因：`freeze / settle / refund / topup / admin_adjust` 均先读用户行再内存修改，缺少 `SELECT ... FOR UPDATE`；业务引用也没有唯一幂等约束
- 实际修复：
  - 账务 mutation 读取 `users` 行时使用 `with_for_update()`
  - `settle()` 更新 API key quota 时锁定 `user_api_keys` 行
  - `freeze / settle / refund / topup` 按 `type + ref_type + ref_id` 做幂等检查
  - 新增迁移 [20260420_10_billing_idempotency_constraints.py](/home/luofei/backend/migrations/user_service/versions/20260420_10_billing_idempotency_constraints.py)，为 `balance_transactions(type, ref_type, ref_id)` 增加唯一键

### P0.6 充值订单重复入账

- 状态：`done`
- 根因：`BalanceService.topup()` 未锁定订单行，也未校验订单必须处于 `PENDING`
- 实际修复：
  - `topup()` 锁定对应 `topup_orders` 行
  - 非 `PENDING` 订单直接抛 `ValidationException`
  - `TYPE_TOPUP + order_no` 流水唯一约束防止重复入账

### P1.1 邀请码补偿 `False` 分支遗漏

- 状态：`done`
- 根因：`register()` 仅在 release 抛异常时写 outbox，release 返回 `False` 被视为成功
- 实际修复：
  - `release_invitation_code()` 返回 `False` 时也会写 `invitation_release_outbox`
  - `last_error` 固定记录为 `release_invitation_code returned false`

### P1.2 验证码过早消费

- 状态：`done`
- 根因：`verify_code_or_raise()` 成功后立即 `used_at + commit`
- 实际修复：
  - 在 `EmailService` 中拆出 `get_valid_code_or_raise()` 与 `mark_code_used()`
  - `register / verify_email / login_with_code / reset_password` 均改为先校验，再在业务条件通过后标记 `used_at`

### P1.3 邮箱验证验证码链路断裂

- 状态：`done`
- 根因：`verify_email()` 读取 `purpose=verify` 的验证码，但 `SendEmailCodeRequest.purpose` 不允许客户端请求 `verify`
- 实际修复：
  - `SendEmailCodeRequest.purpose` 增加 `verify`
  - SMTP 邮件主题/正文为 `verify` 增加独立分支，避免落入 reset-password 文案

### P1.4 禁用用户可重置密码

- 状态：`done`
- 根因：`reset_password()` 找到用户后未检查 `status == 0`
- 实际修复：
  - `reset_password()` 对禁用用户抛 `UserDisabledException`
  - 禁用用户分支不会消费 reset-password 验证码，也不会 commit

### P1.5 用户账务响应字段收敛

- 状态：`done`
- 根因：用户端复用账务/admin schema，导致 `user_id / operator_id / ip` 等内部字段出现在普通用户响应；`/billing/balance` 丢弃 service 已返回的 `frozen_amount`
- 实际修复：
  - `BalanceResponseData` 增加 `frozen_amount` 与计算字段 `available_balance`
  - 用户端 `TopupOrderItem / UsageStatItem / ApiCallLogItem` 移除内部用户 ID、管理员 ID、IP
  - 新增 `AdminTopupOrderItem / AdminUsageStatItem / AdminApiCallLogItem` 保留管理员接口需要的内部字段

### P2.1 `lang` 校验不生效

- 状态：`done`
- 根因：字段顺序导致 validator 读取不到 `lang`
- 实际修复：
  - `RegisterRequest / ChangePasswordRequest / ResetPasswordRequest` 改为 `model_validator(mode="after")`
  - 英文请求现在会返回英文密码强度错误

### P2.2 邮箱规范化缺失

- 状态：`done`
- 根因：模型注释要求 lowercase/trim，但 service 和 schema 未执行
- 实际修复：
  - 新增 `user_service.utils.email.normalize_email()`
  - schema 在入参校验前统一 `strip + lower`
  - `AuthService` 和 `EmailService` 也在内部再次 normalize 做兜底

### P2.3 注册审计信息缺失

- 状态：`done`
- 根因：注册 endpoint 不从 `Request` 提取请求元数据
- 实际修复：
  - 注册 endpoint 增加 `request_obj: Request`
  - 自动登录前会像 `/auth/login` 一样提取 `user-agent` 与客户端 IP

### P2.4 本地外键约束缺失

- 状态：`done`
- 根因：`balance_transactions / topup_orders / api_call_logs / usage_stats` 未对本库内 `users / user_api_keys` 建立本地 FK
- 实际修复：
  - ORM model 已为上述表补充 `ForeignKey`
  - 新增迁移 [20260420_09_add_local_foreign_keys.py](/home/luofei/backend/migrations/user_service/versions/20260420_09_add_local_foreign_keys.py)
  - `api_key_id` 相关 FK 使用 `ON DELETE SET NULL`，保留历史日志

### P2.5 Alembic version 表未推进

- 状态：`done`
- 根因：共享 async Alembic env 在 MySQL 下执行 migration 后没有显式提交 SQLAlchemy async connection；DDL 自动提交已生效，但 `UPDATE alembic_version ...` 被连接退出时 rollback
- 实际修复：
  - [migrations/_env_shared.py](/home/luofei/backend/migrations/_env_shared.py) 的 online 路径在 `await connection.run_sync(do_run_migrations)` 后新增 `await connection.commit()`
  - 新增回归测试锁定共享 env 必须显式提交版本表更新
  - 已重新执行 `user-service` upgrade，当前 revision 为 `20260420_09_add_local_foreign_keys (head)`

### P2.6 pending 用户登录态防御

- 状态：`done`
- 根因：`get_current_user()` 只拒绝 `status=0`，未拒绝 `status=2`
- 实际修复：
  - `get_current_user()` 对 `status=2` 抛 `EmailNotVerifiedException`
  - 防止未来其他路径误发 token 给 pending 用户后访问登录态接口

### P2.7 验证码登录不清理密码失败状态

- 状态：`done`
- 根因：`login_with_code()` 认证成功后未重置 `login_fail_count / login_locked_until`
- 实际修复：
  - 验证码登录成功后清零 `login_fail_count`
  - 验证码登录成功后清空 `login_locked_until`

### P2.8 usage 查询窗口和 account bucket 唯一性

- 状态：`done`
- 根因：`/billing/usage/logs` 默认无时间范围，`/billing/usage` 可查询任意跨度；`usage_stats` 唯一键包含 nullable `api_key_id`，MySQL 允许多条 NULL 破坏 account bucket 唯一性
- 实际修复：
  - 用户端 usage/stats 与 usage/logs 默认查询最近 30 天
  - 用户端 usage/stats 与 usage/logs 最大跨度限制为 90 天
  - `usage_stats` 新增普通列 `account_api_key_id=IFNULL(api_key_id,0)` 并建立 `uk_usage_stats_bucket_effective`
  - 聚合写入新 bucket 时同步设置 `account_api_key_id`

## 验证记录

- 红灯验证：
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py -k 'send_email_code_request_rejects_unknown_purpose or send_email_code_raises_when_service_reports_failure or send_verification_code_does_not_persist_on_email_send_failure or verify_email_rejects_disabled_user or change_password_commits_once_after_revoking_sessions or login_commits_once_for_session_rotation' -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py -k 'release_returns_false or reset_password_does_not_consume_code_when_user_missing' -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py -k 'normalizes_email or uses_lang_for_password_errors or register_endpoint_passes_request_metadata_to_login' -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py -k 'extended_user_models_use_local_foreign_keys' -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py -k 'send_email_code_request_accepts_verify_purpose or change_password_commits_once_after_revoking_sessions or login_with_code_resets_password_failure_lock_state or reset_password_rejects_disabled_user_without_consuming_code or reset_password_commits_after_revoking_sessions or get_current_user_rejects_pending_user' -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user_rebuild.py -k 'freeze_locks_user_row or topup_rejects_already_paid_order or balance_response_exposes_available or user_billing_response_schemas_do_not_expose_internal_ids or billing_usage_logs_default_to_recent_window or billing_usage_rejects_time_ranges_over_90_days' -v`
- 绿灯验证：
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py tests/test_schema_ownership.py tests/test_architecture_boundaries.py -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py tests/test_user_rebuild.py tests/test_backend_app.py tests/test_schema_ownership.py tests/test_architecture_boundaries.py tests/test_migration_structure.py -v`
  - `uv --cache-dir /tmp/uv-cache run pytest tests/test_user.py tests/test_user_rebuild.py tests/test_backend_app.py tests/test_schema_ownership.py tests/test_schema_drift.py tests/test_architecture_boundaries.py tests/test_migration_structure.py -v`
  - `timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service user-service upgrade head`
- 最终结果：
  - `68 passed, 1 skipped, 3 warnings`
  - `timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service user-service current --verbose` 显示 `Rev: 20260420_10_billing_idempotency_constraints (head)`
