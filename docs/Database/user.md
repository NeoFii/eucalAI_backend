# user 模块数据库设计分析

> 更新：2026-04-19
> 范围：`src/user_service/`、`migrations/user_service/versions/`、`eucal_ai_user` 库
> 关联文档：`docs/DATABASE.md`（全库清单）、`docs/schema-ownership.md`

---

## 1. 模块定位

user 是整个后端**依赖链的最底层**：

| 方向 | 关系 | 说明 |
|---|---|---|
| 内部 FK | 只在本库 3 张表之间 | `users` ← `user_sessions` ← `user_active_sessions`（僵尸表）|
| 出向（跨库引用） | 无 | user 表里没有任何字段指向其他库 |
| 入向（被其他库引用） | `admin.invitation_codes.used_by` → `users.uid` | 唯一的反向单点引用 |
| HMAC 出向调用 | user → admin（消费/释放邀请码） | 仅注册流程用 |
| HMAC 入向被调用 | admin / router → user | 查用户详情、用户总数 |

**含义**：user 是"真正的根"。其 schema 变更几乎不会波及其他模块；拆分 DB 时从它下手成本最低。

对外公开的接口面（`api/v1/endpoints/internal.py`）：

- `GET /internal/users/{uid}`：按 uid 查用户（allowed_callers={admin-service, router-service}）
- `GET /internal/users/by-id/{user_id}`：按 id 查用户
- `GET /internal/stats/users`：总用户数

---

## 2. 表清单与结构

### 2.1 总览

```
┌─────────────────────────────────────┐
│              users                  │ ← 账户实体
│  PK id (Snowflake)                  │
│  UK uid / email                     │
│  status ∈ {0,1,2}                   │
│  login_fail_count + login_locked_until  ← 防爆破
└──────┬──────────────────────────────┘
       │
       ├─ 1:N ─► user_sessions (refresh 会话池)
       │        PK id / UK session_id / UK token_jti
       │        user_id FK CASCADE
       │        revoked_at, expires_at
       │
       └─ 1:1 ─► user_active_sessions  ⚠ 僵尸表（无代码读写）
                PK = FK user_id
                FK session_id → user_sessions.session_id (UK, not PK)

┌─────────────────────────────────────┐
│      email_verification_codes       │ ← 与 users 无 FK
│  PK id (自增)                       │
│  email / purpose / code_hash        │
│  purpose ∈ {register, login, verify,│
│              reset_password}        │
│  error_count + locked_until          │
└─────────────────────────────────────┘
```

### 2.2 `users`

终端用户账户。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | 内部主键 |
| `uid` | BIGINT | UNIQUE, INDEXED | 对外 UID（跨库引用目标）|
| `email` | VARCHAR(255) | UNIQUE, INDEXED | 写入前 lowercase + trim |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt |
| `status` | SMALLINT | DEFAULT 1 | 0=disabled / 1=active / 2=pending |
| `email_verified_at` | DATETIME | NULL | 验证时间 |
| `last_login_at` / `last_login_ip` | DATETIME / VARCHAR(45) | NULL | 登录审计 |
| `login_fail_count` | INT | DEFAULT 0 | 连续失败次数 |
| `login_locked_until` | DATETIME | NULL | 锁定到期 |
| `created_at` / `updated_at` | DATETIME | Mixin | — |

**属性**：
- `is_active` = `status == 1`
- `is_email_verified` = `email_verified_at IS NOT NULL`
- `is_login_locked` = `login_locked_until > now()`

### 2.3 `user_sessions`

Refresh-token 会话池。一个用户可以有多条（不同设备或历史登录），当前实现登录时全部撤销。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | Snowflake | — |
| `session_id` | BIGINT | UNIQUE, INDEXED | 对外会话 id |
| `user_id` | BIGINT FK→users.id | ON DELETE CASCADE, INDEXED | 删用户级联 |
| `token_jti` | VARCHAR(64) | UNIQUE, INDEXED | refresh token jti hash |
| `refresh_token_hash` | VARCHAR(255) | NOT NULL | refresh token bcrypt |
| `user_agent` / `ip_address` | VARCHAR(512) / VARCHAR(45) | NULL | 来源审计 |
| `expires_at` | DATETIME | NOT NULL | 到期 |
| `revoked_at` | DATETIME | NULL | 撤销时间；NULL = 未撤销 |
| `created_at` / `updated_at` | DATETIME | Mixin | — |

**双重校验**：先靠 `token_jti` UK 索引快速定位，再用 `verify_password(refresh_token, refresh_token_hash)` 防 jti 碰撞伪造。refresh token 本身只存 hash，不明文落库。

### 2.4 `user_active_sessions`（⚠ 僵尸表）

设计意图是"每用户最多一条活跃会话"的映射（登录互踢语义）。**当前无代码读写**（详见 §3）。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `user_id` | BIGINT PK, FK→users.id | ON DELETE CASCADE | 主键 |
| `session_id` | BIGINT, FK→user_sessions.session_id | ON DELETE CASCADE, UNIQUE | 指向"当前活跃"那条 |
| `updated_at` | DATETIME | DEFAULT/ONUPDATE now | 最后活跃时间 |

**注意**：FK 目标是 `user_sessions.session_id`（UK），不是 `user_sessions.id`（PK）。这是故意的——`session_id` 是对外暴露的稳定 ID，refresh token rotation 不变它。

### 2.5 `email_verification_codes`

邮箱验证码，支持 4 种用途。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT PK | AUTO_INCREMENT | — |
| `email` | VARCHAR(255) | NOT NULL | 与 users 无 FK（码可发给未注册邮箱） |
| `code_hash` | VARCHAR(255) | NOT NULL | 6 位数字 bcrypt hash |
| `purpose` | VARCHAR(20) | DEFAULT 'register' | `register` / `login` / `verify` / `reset_password` |
| `expires_at` | DATETIME | NOT NULL | 过期 |
| `used_at` | DATETIME | NULL | 已使用 |
| `error_count` | INT | DEFAULT 0 | 错误累计（每条码独立） |
| `locked_until` | DATETIME | NULL | 该条码的错误锁到期 |
| `created_at` | DATETIME | DEFAULT now | 无 `updated_at` |

**索引**：
- `idx_codes_email`
- `idx_codes_email_purpose`
- `idx_codes_expires_at` ← 当前无代码使用，为未来清理任务预留

---

## 3. 核心发现：`user_active_sessions` 是僵尸表

### 3.1 现状

```
grep UserActiveSession src/
└── 仅在以下位置出现：
    ├── models/user_active_session.py        （定义）
    ├── models/__init__.py                   （导入注册）
    ├── models/user.py:45                    （relationship）
    ├── models/user_session.py:35            （back_populates）
    └── tests/test_schema_*.py               （schema 漂移检查）

grep UserActiveSession services/ endpoints/
└── 0 matches
```

**零业务代码读写这张表**。schema 存在、ORM 有双向 relationship、测试里注册为该库表集合之一，但 service 层和 endpoint 层完全不碰。

### 3.2 互踢机制的真实实现

`src/user_service/services/auth_service.py::_revoke_all_user_sessions`：

```python
async def _revoke_all_user_sessions(db, user_id):
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    for session in result.scalars().all():
        session.revoked_at = now()
    await db.commit()
```

每次 `login`、`login_with_code`、`change_password`、`reset_password` 都调用它——**把该用户所有未撤销 session 全部标 revoked**，然后插一条新的。等效 "单活跃会话" 策略。

### 3.3 设计 vs 实现的分叉

| 角度 | 表设计期望 | 实际代码 |
|---|---|---|
| 语义 | 保留多会话历史 + 单点"当前活跃" | 新登录直接把所有旧会话 revoke |
| 活跃会话查询 | `JOIN user_active_sessions` 一次命中 | `WHERE user_id=? AND revoked_at IS NULL` 扫子集 |
| 同用户多设备 | 支持 | **不支持**——登录必踢 |

### 3.4 处理建议（三选一，必选）

- **A 删除（推荐）**：写迁移删 `user_active_sessions` 表；移除 `models/user_active_session.py` 及两端 relationship；更新 `tests/test_schema_ownership.py` / `test_schema_drift.py` 的表清单。最干净。
- **B 启用**：改 `_revoke_all_user_sessions` 为 `_revoke_session(active.session_id)`，插新 session 后 upsert `user_active_sessions` 指针——真正实现多设备。
- **C 文档化**：在 `docs/schema-ownership.md` 显式标注 "predefined for multi-device, currently unused"，避免下一任迷惑。

**推荐 A 的理由**：当前 schema 里放着一张无人用的表 + 一个 1:1 relationship + 两端 `lazy="selectin"`，每次 load `User` / `UserSession` 都附带无效 JOIN。启用多设备是产品决策；不决策就删，后续需要再加。

---

## 4. 数据流拆解

### 4.1 注册：两阶段 + 补偿回滚

```
1. SELECT users WHERE email=?              → 已存在则拒
2. check_password_strength                 → 弱密码拒
3. verify_code_or_raise("register")        → 验证码校验 + 标 used（落 commit）
4. 生成 uid (snowflake)
5. HMAC → admin: consume_invitation_code(code, uid)   ← 跨库消费
6. INSERT users (status=1, email_verified_at=now)
7. commit
   IF commit fails:
      rollback
      HMAC → admin: release_invitation_code(code, uid)  ← 补偿
      raise
```

**关键设计**：
- **uid 在插 user 前就生成**：admin 消费邀请码需要 uid，而 user 行还没入库。这解释了为什么 `invitation_codes.used_by` 存 uid 不存 id。
- **commit 失败走补偿**：不是 SAGA，不是 outbox，是最朴素的 try/except + 反向调用。补偿调用本身如果也失败，邀请码会永久 "卡在已用"。
- **验证码在第 3 步就消费**：后面 4~6 任意一步失败，验证码已废，用户需重发。体验代价换防重放。

### 4.2 登录：防爆破 + 强互踢

```
1. SELECT users WHERE email=?              → 不存在：InvalidCredentials
2. user.is_login_locked?                   → 锁定中：拒（带剩余分钟）
3. verify_password 失败：
     login_fail_count++
     IF fail_count >= 5:                     ← LOGIN_MAX_FAILURES
        login_locked_until = now + 1h        ← LOGIN_LOCK_DURATION_HOURS
     commit
     raise InvalidCredentials
4. status==0 (disabled) / status==2 (pending) → 对应异常
5. 成功路径：
     login_fail_count = 0
     login_locked_until = None
     _revoke_all_user_sessions(user.id)    ← 互踢
     生成 access_token + refresh_token
     INSERT user_sessions
     user.last_login_at/ip = now/ip
     commit（单事务）
```

**关键设计**：
- 常量 `LOGIN_MAX_FAILURES=5`、`LOGIN_LOCK_DURATION_HOURS=1` 硬编码在 `auth_service.py` 模块顶部。要调得改代码。
- `login_fail_count` 是累积的：锁定解除后是否重置取决于下次结果。成功路径显式 `=0`，失败路径继续 `+1`。连续锁 → 解锁 → 再错 → `6 >= 5` → 再锁。数字容易误导但逻辑正确。
- **互踢 + 新 session 插入在同一 commit**。失败 rollback 回旧状态，不会出现"被踢还没踢干净"的中间态。

### 4.3 登出

```
1. token_jti = hash(refresh_token JTI)
2. SELECT user_sessions WHERE token_jti=?   ← UK 索引命中
3. verify_password(refresh_token, session.refresh_token_hash)
4. is_revoked?                              ← 已撤销返回 SessionNotFound（非 Revoked）
5. revoked_at = now
```

已撤销 session 统一回 `SessionNotFound` 而不是 `SessionRevoked`——降低攻击者可感知的信息面。

### 4.4 刷新：refresh-token rotation

```
1. decode_token(refresh) → payload
2. payload.type == "refresh"?
3. 按 jti 查 session → hash 校验
4. is_revoked / is_expired → 对应异常
5. SELECT users WHERE id=session.user_id → status==1?
6. 生成新 access + 新 refresh
7. session.token_jti = 新 jti hash
   session.refresh_token_hash = 新 refresh hash
   session.expires_at = now + 7d
   commit
```

**关键设计**：
- **每次刷新都轮换 refresh token**：老 token 自然失效（jti 查不到）。
- `session.id` 和 `session_id` UK 都不变，只换 jti / hash / expires_at。这是 `user_active_sessions.session_id` 可以安全作为 FK 目标的前提——稳定性比 jti 高一个层级。

### 4.5 验证码：多 purpose + 日频限 + 错误锁

**发送** (`send_verification_code`)：
```
1. 当日同 (email, purpose) 发送计数 >= 3 → 拒
2. 最近一条若 locked_until 未到 → 拒（错误锁期间不发新码）
3. 删除同 (email, purpose) 下所有 未使用 的旧码
4. INSERT 新码（bcrypt hash 6 位数字）
5. SMTP 发送 → commit
```

**校验** (`verify_code_or_raise`)：
```
1. 取最近一条 未使用 的 (email, purpose) 码
2. locked? 拒
3. 过期? 拒
4. hash 不匹配：
     error_count++
     IF error_count >= 5:                  ← MAX_CODE_ERRORS
        locked_until = now + 24h           ← ERROR_COUNT_EXPIRE_HOURS
     raise
5. 成功：used_at = now, error_count = 0
```

**关键设计**：
- 每次只认"最近那条未使用码"。发送前清旧未用码，保证"最近一条"语义明确。
- 错误锁是**每条码独立**的 `locked_until`，不是 email 维度。但 "最近一条锁定就拒发新码" 等效于阻止该 (email, purpose) 的新申请。
- 6 位数字 bcrypt 慢（~100ms），但这是 login 级调用，可接受。
- **无过期清理任务**：只插入 / 更新，没见 TTL DELETE。长期运行会累积。

### 4.6 改密 / 重置：统一强互踢

`change_password` / `reset_password` 完成后强制 `_revoke_all_user_sessions` ——所有设备强制重新登录。对单设备用户合理，对多设备用户是痛点，再次印证当前的"单活跃会话"策略。

---

## 5. 索引与约束作用点

| 索引 / 约束 | 命中场景 | 评价 |
|---|---|---|
| `users.email UNIQUE + INDEX` | 注册查重、登录、验证码后 SELECT | 必需 |
| `users.uid UNIQUE + INDEX` | HMAC 反查 `/internal/users/{uid}` | 热路径 |
| `user_sessions.token_jti UNIQUE + INDEX` | logout / refresh 主查询 | 热路径 |
| `user_sessions.session_id UNIQUE` | 对外暴露 id；`user_active_sessions` FK 目标 | 僵尸表启用前利用率低 |
| `user_sessions.user_id INDEX` | `_revoke_all_user_sessions` 扫集合 | 每次登录命中 |
| `user_active_sessions` 整张 | — | 僵尸 |
| `email_verification_codes idx_codes_email` / `email_purpose` | 发送计数、最近码查询 | 热路径 |
| `email_verification_codes idx_codes_expires_at` | 无代码使用 | 预留清理任务 |

### FK 目标非 PK 的隐式约束

`user_active_sessions.session_id` FK 指向 `user_sessions.session_id`（UK）而不是 PK。
- 语义上 "一个 session 只能被 active 表指一次" 靠 `user_active_sessions.session_id UNIQUE` 保证。
- 如果将来 `user_sessions.session_id` 改语义（比如允许重复、拆段），这条 FK 会先挡住。算是隐式约束放大器。
- MySQL / PostgreSQL 均支持 FK 指向 UK，迁库无兼容问题。

---

## 6. 潜在问题与改进（按优先级）

### P0 —— 立刻决策

1. **僵尸表 `user_active_sessions`**：按 §3.4 三选一。**推荐删除**。

### P1 —— 影响正确性 / 运维

2. **`email_verification_codes` 无 TTL 清理**
   - 风险：每次注册 / 登录 / 改密都写一行；一年后几十万到百万行；`idx_codes_email` 查询仍快，但备份 / 迁移 / 审计成本递增。
   - 修：加 arq 定时任务，每天 `DELETE WHERE expires_at < now() - INTERVAL 7 DAY AND used_at IS NOT NULL`。`idx_codes_expires_at` 已经存在，正是为此。

3. **邀请码补偿失败无兜底**
   - 风险：`register` 里 `release_invitation_code` 如果连不上 admin，邀请码永久 "已用"；用户注册没成功但码废了。
   - 修：补偿调用包 retry；失败后写一张 `invitation_release_outbox` 表，由定时 worker 消费。

### P2 —— 可读性 / 一致性

4. **硬编码魔数**：`LOGIN_MAX_FAILURES=5` / `LOGIN_LOCK_DURATION_HOURS=1` / `MAX_CODE_ERRORS=5` / `ERROR_COUNT_EXPIRE_HOURS=24` / 每日发送 3 次上限 分散在 `auth_service.py` 和 `email_service.py`。
   - 修：统一提到 `user_service/config.py` 的 `Settings` 里走 `.env`。

5. **`users.email` 规范化依赖 Pydantic 层**
   - 现状：`auth_service.register` 内没看到显式 `data.email = data.email.strip().lower()`。需确认 `schemas.RegisterRequest.email` 是否走 `EmailStr` + validator 做规范化。
   - 修：如果 schema 层没做，补上 validator 或在 service 入口显式规范化；否则不同路径可能写入大小写不一的 email，`UNIQUE` 在 MySQL 默认 collation 下查得到但 Postgres 会翻车。

6. **注册流程验证码在 admin 调用前就 used**
   - 现状：`verify_code_or_raise` 内部 commit 把 `used_at` 落地；随后 admin consume 失败虽 raise，但验证码已废。用户要再等冷却期重发。
   - 权衡：延后标 used 需要事务跨 HTTP 边界变长。保留现状可接受，但文档化提醒。

### P3 —— 长期

7. **多设备产品决策**：如果确定支持多设备，`user_active_sessions` 启用路径明确：`_revoke_all_user_sessions` 改为 `_revoke_session(active.session_id)`，新 session 插入后 upsert active 指针。
8. **迁移 PostgreSQL 审查点**：
   - `users.email` 规范化必须在写入端落地（见 P2 #5）
   - 所有 `DateTime` naive → `TIMESTAMPTZ`
   - `code_hash` / `password_hash` bcrypt 跨平台无兼容问题
   - `user_sessions.session_id` UK 作为 FK 目标在 PG 下行为一致，无需改动

---

## 7. 一句话总结

user 模块 schema 设计周全（防爆破、验证码多 purpose、refresh-token rotation、邀请码补偿），但 **`user_active_sessions` 僵尸表** 和 **验证码表无 TTL 清理** 是两个必须处理的技术债；其余都是 P2 级改进。
