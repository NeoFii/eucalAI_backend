# User Service 重构规范文档

> 文档用途：指导模型对 user-service 进行全面重构，包含清理技术债、扩展余额与用量体系、明确服务边界。
> 适用范围：`src/user_service/`、`migrations/user_service/versions/`、`eucal_ai_user` 库
> 关联服务：`router-service`（计费执行方）、`admin-service`（邀请码管理）

---

## 一、总体原则

1. **服务边界清晰**：user-service 管账户生命周期、余额账本、API Key CRUD、充值订单；router-service 管实际调用计费、token 计数、调用日志写入；双方通过 HMAC 内部接口通信。
2. **余额唯一来源**：所有扣费统一走 `users.balance`，API Key 的 `quota_limit` 仅是消费熔断上限，不做资金划拨。
3. **余额单位**：人民币"分"，`INT` 存储，`100 = ¥1.00`，全链路禁止浮点运算。
4. **只保留 merged 部署模式**：删除 standalone 相关代码，以 `backend_app.main:app` 为唯一入口。
5. **MySQL 锁定**：不考虑迁移 PostgreSQL，所有设计基于 MySQL 5.7+。

---

## 二、清理任务（先于功能扩展执行）

### 2.1 删除僵尸表 `user_active_sessions`

**操作步骤：**

1. 新建迁移文件，执行 `DROP TABLE IF EXISTS user_active_sessions`
2. 删除 `src/user_service/models/user_active_session.py`
3. 在 `models/user.py` 中删除 `active_session` relationship
4. 在 `models/user_session.py` 中删除 `active_session` back_populates
5. 更新 `tests/test_schema_ownership.py` 和 `tests/test_schema_drift.py` 的表清单，移除 `user_active_sessions`

**验证：** 运行 schema drift 测试，确认通过。

### 2.2 删除 standalone 部署相关代码

**操作步骤：**

1. 删除 `src/user_service/services/content_client.py`
2. 删除 `src/user_service/api/v1/endpoints/news.py`（若存在）
3. 删除路由注册中 news 相关的 `include_router` 调用
4. 在 `config.py` 中删除 `CONTENT_SERVICE_URL` 配置项
5. 检查 `user_service/main.py`，如果是 standalone 入口则整个文件删除，确保只保留 `backend_app/main.py` 作为入口

**验证：** 启动 `backend_app`，确认 `/api/v1/news/*` 路由不存在（返回 404）。

### 2.3 删除 RouterApiKey 孤岛 schemas

**操作步骤：**

1. 在 `schemas.py` 中删除以下 11 个类（行号仅供参考，以实际文件为准）：
   - `RouterApiKeyItem`
   - `RouterApiKeyCreateRequest`
   - `RouterApiKeyUpdateRequest`
   - `RouterApiKeyListResponse`
   - `RouterApiKeyListData`
   - `RouterApiKeyCreateResponse`
   - `RouterApiKeyCreateData`
   - `RouterApiKeyUpdateResponse`
   - `RouterApiKeyRevealResponse`
   - `RouterApiKeyRevealData`
   - `RouterApiKeyDeleteResponse`
2. 在 `config.py` 中删除 `ROUTER_SERVICE_URL` 配置项

**验证：** 全量运行测试，确认无 import 错误。

### 2.4 清理未使用的依赖注入函数

**操作步骤：**

1. 确认 `get_optional_user` 和 `require_active_user` 在所有 endpoint 文件中均无引用
2. 若确认无引用，从 `dependencies.py`（或对应文件）中删除这两个函数
3. 若有测试文件 import 这两个函数（仅测试存在性），同步删除对应测试用例

### 2.5 清理未使用内部接口

**操作步骤：**

1. 确认 `GET /internal/users/by-id/{user_id}` 是否有实际调用方（查 admin-service 和 router-service 代码）
2. 若无调用方，删除该 endpoint 及对应 service 方法
3. 若有调用方，在代码中添加注释说明调用场景

---

## 三、数据库扩展

### 3.1 `users` 表新增字段

新建迁移文件，添加以下字段：

```sql
ALTER TABLE users
    ADD COLUMN balance        INT    NOT NULL DEFAULT 0 COMMENT '可用余额（分，¥1=100）',
    ADD COLUMN frozen_amount  INT    NOT NULL DEFAULT 0 COMMENT '预冻结中的余额（分）',
    ADD COLUMN used_amount    INT    NOT NULL DEFAULT 0 COMMENT '历史累计消费（分）',
    ADD COLUMN total_requests INT    NOT NULL DEFAULT 0 COMMENT '历史累计调用次数',
    ADD COLUMN total_tokens   BIGINT NOT NULL DEFAULT 0 COMMENT '历史累计 token 数';
```

**字段语义说明：**
- `balance`：用户当前可操作的余额，不包含 `frozen_amount`。用户看到的余额展示值即为此字段。
- `frozen_amount`：三段式计费中"预冻结"阶段从 `balance` 转入此处，结算后归零。任何时候 `balance + frozen_amount` = 总资产（不含历史消费）。
- `used_amount`：只增不减，每次结算后累加实际扣费金额，用于用户总消费统计。
- `total_requests` / `total_tokens`：冗余统计字段，结算时同步递增，避免实时聚合 log 表。

### 3.2 新建 `user_api_keys` 表

```sql
CREATE TABLE user_api_keys (
    id              BIGINT        NOT NULL            COMMENT 'Snowflake PK',
    user_id         BIGINT        NOT NULL            COMMENT 'FK → users.id',
    key_hash        VARCHAR(128)  NOT NULL            COMMENT 'SHA-256(原始key)，router 校验用',
    key_prefix      VARCHAR(12)   NOT NULL            COMMENT '前8位明文，前端展示用',
    name            VARCHAR(100)  NOT NULL            COMMENT '用户自定义名称',

    status          TINYINT       NOT NULL DEFAULT 1  COMMENT '1=active 2=disabled 3=expired 4=exhausted',

    quota_mode      TINYINT       NOT NULL DEFAULT 1  COMMENT '1=unlimited 2=limited',
    quota_limit     INT           NOT NULL DEFAULT 0  COMMENT 'mode=2时的消费上限（分），mode=1时忽略',
    quota_used      INT           NOT NULL DEFAULT 0  COMMENT '该key累计已消费（分），两种模式都记录',

    allowed_models  TEXT          NULL                COMMENT 'NULL=不限，否则逗号分隔模型名',
    allow_ips       TEXT          NULL                COMMENT 'NULL=不限，否则换行分隔CIDR',

    expires_at      DATETIME      NULL                COMMENT 'NULL=永不过期',
    last_used_at    DATETIME      NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE  KEY uk_key_hash   (key_hash),
    INDEX        idx_user_id  (user_id),
    INDEX        idx_status   (status)
) COMMENT='用户 API Key 表';
```

**配额模式说明：**
- `mode=1（unlimited）`：key 无消费上限，每次调用直接从 `users.balance` 扣费。`quota_used` 仍然记录，仅供统计。
- `mode=2（limited）`：key 有消费上限 `quota_limit`。router 在调用前检查 `quota_used >= quota_limit`，满足则拒绝并返回"当前 key 额度已耗尽"。实际扣费**仍走 `users.balance`**，不做任何资金划拨。
- key 额度用尽后状态变为 `exhausted`，用户可通过调高 `quota_limit` 或重置 `quota_used` 重新激活。

### 3.3 新建 `balance_transactions` 表

```sql
CREATE TABLE balance_transactions (
    id              BIGINT        NOT NULL            COMMENT 'Snowflake PK',
    user_id         BIGINT        NOT NULL            COMMENT 'FK → users.id',
    type            TINYINT       NOT NULL            COMMENT '见下方枚举',
    amount          INT           NOT NULL            COMMENT '正=增加 负=减少（分）',
    balance_before  INT           NOT NULL            COMMENT '变动前 users.balance 快照',
    balance_after   INT           NOT NULL            COMMENT '变动后 users.balance 快照',

    ref_type        VARCHAR(32)   NULL                COMMENT 'topup_order / api_call',
    ref_id          VARCHAR(64)   NULL                COMMENT '关联单据 id（充值单id / request_id）',

    remark          VARCHAR(255)  NULL                COMMENT '管理员备注 / 系统描述',
    operator_id     BIGINT        NULL                COMMENT '管理员操作人uid（type=6时有值）',

    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_user_created  (user_id, created_at),
    INDEX idx_type_created  (type, created_at),
    INDEX idx_ref           (ref_type, ref_id)
) COMMENT='余额流水账本';
```

**type 枚举：**

| 值 | 常量名 | 说明 |
|---|---|---|
| 1 | `TOPUP` | 充值（管理员手动 / 后续支付宝微信） |
| 2 | `CONSUME` | API 调用消费（三段式结算写入） |
| 3 | `REFUND` | 调用失败全额退款 |
| 4 | `FREEZE` | 预冻结（请求发出前，从 balance 转入 frozen_amount） |
| 5 | `UNFREEZE` | 解冻（与 CONSUME 同事务，将 freeze 部分归还） |
| 6 | `ADMIN_ADJUST` | 管理员手动调整余额（增减均可） |

**freeze/unfreeze 配对机制：**

每次 API 调用写一条 `type=FREEZE`，`ref_id=request_id`，`amount=-估算金额`。
结算时在同一事务中写：
- `type=UNFREEZE`，`amount=+估算金额`（解冻）
- `type=CONSUME`，`amount=-实际金额`（扣费）

失败时写：
- `type=REFUND`，`amount=+估算金额`（全额退还）

任何时刻可以通过流水重算 `balance`，完整对账。

### 3.4 新建 `topup_orders` 表

```sql
CREATE TABLE topup_orders (
    id               BIGINT        NOT NULL            COMMENT 'Snowflake PK',
    order_no         VARCHAR(64)   NOT NULL            COMMENT '业务单号，格式：TP{yyyyMMdd}{8位随机}',
    user_id          BIGINT        NOT NULL            COMMENT 'FK → users.id',

    amount           INT           NOT NULL            COMMENT '充值金额（分）',
    status           TINYINT       NOT NULL DEFAULT 1  COMMENT '1=pending 2=paid 3=cancelled 4=refunded',

    payment_channel  VARCHAR(32)   NOT NULL DEFAULT 'manual'
                                                       COMMENT 'manual / alipay / wechat / stripe',
    payment_no       VARCHAR(128)  NULL                COMMENT '第三方支付流水号（预留）',
    payment_raw      JSON          NULL                COMMENT '第三方回调原始报文（预留，留存对账）',
    paid_at          DATETIME      NULL,

    remark           VARCHAR(255)  NULL                COMMENT '管理员备注',
    operator_id      BIGINT        NULL                COMMENT '手动充值时的管理员uid',

    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE  KEY uk_order_no   (order_no),
    INDEX        idx_user_id  (user_id, created_at),
    INDEX        idx_status   (status)
) COMMENT='充值订单表';
```

### 3.5 新建 `api_call_logs` 表（由 router-service 写入）

> 此表在 user-service 数据库中定义，但由 router-service 通过 HMAC 接口写入。user-service 提供只读查询接口。

```sql
CREATE TABLE api_call_logs (
    id                  BIGINT        NOT NULL            COMMENT 'Snowflake PK',
    request_id          VARCHAR(64)   NOT NULL            COMMENT '全局唯一请求ID，贯穿三段式计费',

    user_id             BIGINT        NOT NULL            COMMENT 'FK → users.id',
    api_key_id          BIGINT        NULL                COMMENT 'FK → user_api_keys.id，NULL=未使用key',

    model_name          VARCHAR(64)   NOT NULL,
    prompt_tokens       INT           NOT NULL DEFAULT 0,
    completion_tokens   INT           NOT NULL DEFAULT 0,
    cached_tokens       INT           NOT NULL DEFAULT 0  COMMENT '命中缓存的token数',
    total_tokens        INT           NOT NULL DEFAULT 0,

    cost                INT           NOT NULL DEFAULT 0  COMMENT '用户侧实际扣费汇总（分）',
    cost_detail         JSON          NULL,
    -- cost_detail 结构：
    -- {
    --   "input_unit_price":  10,     分/千token
    --   "output_unit_price": 30,     分/千token
    --   "cache_unit_price":  2,      分/千token（命中缓存单价）
    --   "input_cost":        5,      分
    --   "output_cost":       18,     分
    --   "cache_cost":        1,      分
    --   "markup_rate":       1.2     平台加价倍率
    -- }
    -- 注意：cost_detail 仅管理员可见，普通用户查询时 service 层裁掉此字段

    status              TINYINT       NOT NULL DEFAULT 1  COMMENT '1=success 2=error 3=refunded',
    duration_ms         INT           NULL                COMMENT '请求耗时（毫秒）',
    is_stream           TINYINT(1)    NOT NULL DEFAULT 0,
    ip                  VARCHAR(45)   NULL                COMMENT '受用户 record_ip 设置控制',

    error_code          VARCHAR(32)   NULL                COMMENT 'status=2时有值',
    error_msg           VARCHAR(512)  NULL,

    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE  KEY uk_request_id        (request_id),
    INDEX        idx_user_created    (user_id, created_at),
    INDEX        idx_key_created     (api_key_id, created_at),
    INDEX        idx_model_created   (model_name, created_at),
    INDEX        idx_status_created  (status, created_at)
) COMMENT='API调用明细日志，由router-service写入';
```

### 3.6 新建 `usage_stats` 表

```sql
CREATE TABLE usage_stats (
    id              BIGINT        NOT NULL,

    user_id         BIGINT        NOT NULL,
    api_key_id      BIGINT        NULL                COMMENT 'NULL=账户维度汇总；非NULL=单key维度',
    model_name      VARCHAR(64)   NOT NULL,
    stat_hour       DATETIME      NOT NULL            COMMENT '整点，如 2024-01-15 14:00:00',

    request_count   INT           NOT NULL DEFAULT 0,
    success_count   INT           NOT NULL DEFAULT 0,
    error_count     INT           NOT NULL DEFAULT 0,

    prompt_tokens       BIGINT    NOT NULL DEFAULT 0,
    completion_tokens   BIGINT    NOT NULL DEFAULT 0,
    cached_tokens       BIGINT    NOT NULL DEFAULT 0,
    total_tokens        BIGINT    NOT NULL DEFAULT 0,

    total_cost      INT           NOT NULL DEFAULT 0  COMMENT '分',

    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE  KEY uk_stat       (user_id, api_key_id, model_name, stat_hour),
    INDEX        idx_user_hour (user_id, stat_hour),
    INDEX        idx_key_hour  (api_key_id, stat_hour),
    INDEX        idx_hour      (stat_hour)
) COMMENT='小时级用量聚合表，由arq定时任务写入';
```

**聚合维度说明：**

每条 `api_call_logs` 记录生成两行 `usage_stats`：
- `api_key_id = 实际key的id`（单 key 维度）
- `api_key_id = NULL`（账户汇总维度）

写入用 `INSERT ... ON DUPLICATE KEY UPDATE`，利用 `uk_stat` 唯一键保证幂等。

---

## 四、ORM Model 变更

### 4.1 `User` model 新增字段

```python
# models/user.py 新增以下字段
balance        = Column(Integer, nullable=False, default=0)
frozen_amount  = Column(Integer, nullable=False, default=0)
used_amount    = Column(Integer, nullable=False, default=0)
total_requests = Column(Integer, nullable=False, default=0)
total_tokens   = Column(BigInteger, nullable=False, default=0)
```

删除字段：
- 移除 `active_session` relationship（僵尸表清理）

新增属性：
```python
@property
def available_balance(self) -> int:
    """用户可用余额（分），balance 即为可用值，frozen 不展示给用户"""
    return self.balance

@property
def total_assets(self) -> int:
    """总资产 = 可用 + 冻结（内部对账用）"""
    return self.balance + self.frozen_amount
```

### 4.2 新增 `UserApiKey` model

```python
# models/user_api_key.py
class UserApiKey(Base, TimestampMixin):
    __tablename__ = "user_api_keys"

    id             = Column(BigInteger, primary_key=True)
    user_id        = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    key_hash       = Column(String(128), nullable=False, unique=True)
    key_prefix     = Column(String(12), nullable=False)
    name           = Column(String(100), nullable=False)
    status         = Column(SmallInteger, nullable=False, default=1)
    quota_mode     = Column(SmallInteger, nullable=False, default=1)
    quota_limit    = Column(Integer, nullable=False, default=0)
    quota_used     = Column(Integer, nullable=False, default=0)
    allowed_models = Column(Text, nullable=True)
    allow_ips      = Column(Text, nullable=True)
    expires_at     = Column(DateTime, nullable=True)
    last_used_at   = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys", lazy="select")

    # 状态常量
    STATUS_ACTIVE    = 1
    STATUS_DISABLED  = 2
    STATUS_EXPIRED   = 3
    STATUS_EXHAUSTED = 4

    # 配额模式常量
    MODE_UNLIMITED = 1
    MODE_LIMITED   = 2

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE

    @property
    def is_exhausted(self) -> bool:
        if self.quota_mode == self.MODE_UNLIMITED:
            return False
        return self.quota_used >= self.quota_limit

    @property
    def remaining_quota(self) -> int:
        """mode=2 时剩余可用额度（分）；mode=1 返回 -1 表示无限制"""
        if self.quota_mode == self.MODE_UNLIMITED:
            return -1
        return max(0, self.quota_limit - self.quota_used)
```

### 4.3 新增 `BalanceTransaction` model

```python
# models/balance_transaction.py
class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"

    id             = Column(BigInteger, primary_key=True)
    user_id        = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    type           = Column(SmallInteger, nullable=False)
    amount         = Column(Integer, nullable=False)       # 正=增加 负=减少
    balance_before = Column(Integer, nullable=False)
    balance_after  = Column(Integer, nullable=False)
    ref_type       = Column(String(32), nullable=True)
    ref_id         = Column(String(64), nullable=True)
    remark         = Column(String(255), nullable=True)
    operator_id    = Column(BigInteger, nullable=True)
    created_at     = Column(DateTime, nullable=False, default=func.now())

    # type 常量
    TYPE_TOPUP        = 1
    TYPE_CONSUME      = 2
    TYPE_REFUND       = 3
    TYPE_FREEZE       = 4
    TYPE_UNFREEZE     = 5
    TYPE_ADMIN_ADJUST = 6
```

### 4.4 新增 `TopupOrder` model

```python
# models/topup_order.py
class TopupOrder(Base, TimestampMixin):
    __tablename__ = "topup_orders"

    id               = Column(BigInteger, primary_key=True)
    order_no         = Column(String(64), nullable=False, unique=True)
    user_id          = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount           = Column(Integer, nullable=False)
    status           = Column(SmallInteger, nullable=False, default=1)
    payment_channel  = Column(String(32), nullable=False, default="manual")
    payment_no       = Column(String(128), nullable=True)
    payment_raw      = Column(JSON, nullable=True)
    paid_at          = Column(DateTime, nullable=True)
    remark           = Column(String(255), nullable=True)
    operator_id      = Column(BigInteger, nullable=True)

    # status 常量
    STATUS_PENDING   = 1
    STATUS_PAID      = 2
    STATUS_CANCELLED = 3
    STATUS_REFUNDED  = 4

    # payment_channel 常量
    CHANNEL_MANUAL = "manual"
    CHANNEL_ALIPAY = "alipay"
    CHANNEL_WECHAT = "wechat"
    CHANNEL_STRIPE = "stripe"
```

### 4.5 新增 `ApiCallLog` model

```python
# models/api_call_log.py
class ApiCallLog(Base):
    __tablename__ = "api_call_logs"

    id                 = Column(BigInteger, primary_key=True)
    request_id         = Column(String(64), nullable=False, unique=True)
    user_id            = Column(BigInteger, nullable=False)
    api_key_id         = Column(BigInteger, nullable=True)
    model_name         = Column(String(64), nullable=False)
    prompt_tokens      = Column(Integer, nullable=False, default=0)
    completion_tokens  = Column(Integer, nullable=False, default=0)
    cached_tokens      = Column(Integer, nullable=False, default=0)
    total_tokens       = Column(Integer, nullable=False, default=0)
    cost               = Column(Integer, nullable=False, default=0)
    cost_detail        = Column(JSON, nullable=True)
    status             = Column(SmallInteger, nullable=False, default=1)
    duration_ms        = Column(Integer, nullable=True)
    is_stream          = Column(Boolean, nullable=False, default=False)
    ip                 = Column(String(45), nullable=True)
    error_code         = Column(String(32), nullable=True)
    error_msg          = Column(String(512), nullable=True)
    created_at         = Column(DateTime, nullable=False, default=func.now())

    STATUS_SUCCESS  = 1
    STATUS_ERROR    = 2
    STATUS_REFUNDED = 3
```

### 4.6 新增 `UsageStat` model

```python
# models/usage_stat.py
class UsageStat(Base, TimestampMixin):
    __tablename__ = "usage_stats"

    id                = Column(BigInteger, primary_key=True)
    user_id           = Column(BigInteger, nullable=False)
    api_key_id        = Column(BigInteger, nullable=True)  # NULL=账户维度
    model_name        = Column(String(64), nullable=False)
    stat_hour         = Column(DateTime, nullable=False)
    request_count     = Column(Integer, nullable=False, default=0)
    success_count     = Column(Integer, nullable=False, default=0)
    error_count       = Column(Integer, nullable=False, default=0)
    prompt_tokens     = Column(BigInteger, nullable=False, default=0)
    completion_tokens = Column(BigInteger, nullable=False, default=0)
    cached_tokens     = Column(BigInteger, nullable=False, default=0)
    total_tokens      = Column(BigInteger, nullable=False, default=0)
    total_cost        = Column(Integer, nullable=False, default=0)
```

---

## 五、Service 层新增功能

### 5.1 `BalanceService`（新建）

负责所有余额操作，所有写操作必须在数据库事务内执行，并同步写 `balance_transactions` 流水。

```python
class BalanceService:

    @staticmethod
    async def get_balance(db, user_id: int) -> dict:
        """返回用户余额信息（balance / frozen_amount / used_amount）"""

    @staticmethod
    async def freeze(db, user_id: int, amount: int, request_id: str) -> None:
        """
        预冻结：balance -= amount，frozen_amount += amount
        写 balance_transactions(type=FREEZE, ref_type='api_call', ref_id=request_id)
        约束：amount > 0，balance >= amount（不足则 raise InsufficientBalanceError）
        """

    @staticmethod
    async def settle(
        db, user_id: int, request_id: str,
        estimated_amount: int, actual_amount: int,
        api_key_id: int | None = None
    ) -> None:
        """
        结算：同一事务写两条流水
        1. UNFREEZE: frozen_amount -= estimated_amount，balance += estimated_amount
        2. CONSUME:  balance -= actual_amount，used_amount += actual_amount
        若 api_key_id 非 None 且该 key 为 mode=2，同步更新 key.quota_used += actual_amount
        若 quota_used >= quota_limit，将 key.status 更新为 exhausted
        同步递增 users.total_requests += 1，users.total_tokens += actual_tokens（由调用方传入）
        """

    @staticmethod
    async def refund(db, user_id: int, request_id: str, amount: int) -> None:
        """
        退款：frozen_amount -= amount，balance += amount
        写 balance_transactions(type=REFUND, ref_type='api_call', ref_id=request_id)
        幂等：若该 request_id 已有 REFUND 记录则跳过
        """

    @staticmethod
    async def topup(
        db, user_id: int, amount: int,
        order_id: str, operator_id: int, remark: str = ""
    ) -> None:
        """
        充值：balance += amount
        写 balance_transactions(type=TOPUP, ref_type='topup_order', ref_id=order_id)
        同步更新 topup_orders.status = paid，paid_at = now()
        """

    @staticmethod
    async def admin_adjust(
        db, user_id: int, amount: int,
        operator_id: int, remark: str
    ) -> None:
        """
        管理员调整：balance += amount（负值为扣减）
        约束：调整后 balance >= 0（不允许调成负数）
        写 balance_transactions(type=ADMIN_ADJUST)
        """
```

### 5.2 `ApiKeyService`（新建）

```python
class ApiKeyService:

    @staticmethod
    async def create(
        db, user_id: int, name: str,
        quota_mode: int = 1, quota_limit: int = 0,
        allowed_models: str | None = None,
        allow_ips: str | None = None,
        expires_at: datetime | None = None
    ) -> tuple[UserApiKey, str]:
        """
        创建 API Key
        生成 48 位随机原始 key（格式：sk-{46位随机字母数字}）
        存储 key_hash = SHA-256(原始key)，key_prefix = 原始key[:8]
        原始 key 仅在此处返回一次，不落库
        返回 (UserApiKey 实例, 原始key字符串)
        """

    @staticmethod
    async def list(db, user_id: int) -> list[UserApiKey]:
        """列出用户所有 key，返回时不包含 key_hash（仅前端展示用的 key_prefix）"""

    @staticmethod
    async def update_quota(
        db, key_id: int, user_id: int,
        new_quota_limit: int | None = None,
        reset_quota_used: bool = False
    ) -> UserApiKey:
        """
        更新 key 的配额设置
        若 new_quota_limit < 当前 quota_used，则同步将 status 更新为 exhausted
        若 reset_quota_used=True，清零 quota_used 并将 exhausted 状态恢复为 active
        """

    @staticmethod
    async def disable(db, key_id: int, user_id: int) -> None:
        """禁用 key，status 改为 disabled"""

    @staticmethod
    async def delete(db, key_id: int, user_id: int) -> None:
        """删除 key，硬删除"""

    @staticmethod
    async def validate_by_hash(db, key_hash: str) -> UserApiKey | None:
        """
        router-service 调用：通过 key_hash 校验 key 有效性
        返回 key 信息（含 user_id / quota_mode / quota_used / quota_limit / status）
        若 key 不存在 / disabled / expired 返回 None
        若 expired 且未标记，顺便更新 status = expired
        """
```

### 5.3 `TopupOrderService`（新建）

```python
class TopupOrderService:

    @staticmethod
    async def create_manual(
        db, user_id: int, amount: int,
        operator_id: int, remark: str = ""
    ) -> TopupOrder:
        """
        管理员手动充值：
        1. 生成订单 order_no（格式：TP{yyyyMMdd}{8位随机大写字母数字}）
        2. 创建 topup_orders 记录（status=pending）
        3. 调用 BalanceService.topup 完成充值
        4. 更新订单 status=paid
        以上步骤在同一事务内完成
        """

    @staticmethod
    async def get_user_orders(
        db, user_id: int,
        page: int = 1, page_size: int = 20
    ) -> list[TopupOrder]:
        """用户查询自己的充值记录（不含 payment_raw 字段）"""

    @staticmethod
    async def get_all_orders(
        db, page: int = 1, page_size: int = 20,
        user_id: int | None = None,
        status: int | None = None
    ) -> list[TopupOrder]:
        """管理员查询所有充值记录（含 payment_raw）"""
```

### 5.4 `UsageStatService`（新建，arq 定时任务使用）

```python
class UsageStatService:

    @staticmethod
    async def aggregate_hour(db, stat_hour: datetime) -> None:
        """
        聚合指定小时的调用数据：
        从 api_call_logs 按 (user_id, api_key_id, model_name) 分组聚合
        每组生成两行 usage_stats：
          - api_key_id = 实际值（单 key 维度）
          - api_key_id = NULL（账户汇总维度，api_key_id IS NULL 的独立行）
        用 INSERT ... ON DUPLICATE KEY UPDATE 保证幂等
        """

    @staticmethod
    async def get_user_stats(
        db, user_id: int,
        start: datetime, end: datetime,
        model_name: str | None = None,
        api_key_id: int | None = None
    ) -> list[UsageStat]:
        """用户查询自己的用量统计（api_key_id=None 则查账户维度汇总）"""

    @staticmethod
    async def get_all_stats(
        db, start: datetime, end: datetime,
        user_id: int | None = None,
        model_name: str | None = None
    ) -> list[UsageStat]:
        """管理员查询全局统计"""
```

### 5.5 修改邀请码注册流程（P1 优化）

**现有问题**：验证码在第3步就标为 `used_at` 并 commit，后续步骤失败用户需重新等冷却期。

**优化方案**：将验证码消费推迟到注册事务提交成功后。

```
旧流程：
  verify_code_or_raise（内部 commit used_at）→ admin.consume_invitation_code
  → INSERT users → commit → [失败] → admin.release_invitation_code

新流程：
  1. verify_code（仅校验，不标 used_at，不 commit）
  2. admin.consume_invitation_code（HMAC，含 retry 3次）
  3. INSERT users（status=1, email_verified_at=now）
  4. mark_code_used（在同一事务内标 used_at）
  5. commit
  [失败] admin.release_invitation_code（HMAC，失败写 invitation_release_outbox，
          由 arq worker 重试消费，最多 5 次，每次间隔指数退避）
```

新建 `invitation_release_outbox` 表：

```sql
CREATE TABLE invitation_release_outbox (
    id          BIGINT       NOT NULL,
    code        VARCHAR(64)  NOT NULL,
    used_by_uid BIGINT       NOT NULL,
    retry_count INT          NOT NULL DEFAULT 0,
    last_error  VARCHAR(255) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_retry (retry_count, updated_at)
) COMMENT='邀请码释放补偿 outbox，注册失败时写入，由arq worker消费';
```

---

## 六、API 端点新增

### 6.1 用户端（`/api/v1/auth/` 系列）

以下端点在 `api/v1/endpoints/auth.py` 或新建的 `api/v1/endpoints/billing.py` 中实现：

| 方法 | 路径 | 功能 | 鉴权 |
|---|---|---|---|
| `GET` | `/api/v1/billing/balance` | 查询当前余额 | 登录用户 |
| `GET` | `/api/v1/billing/transactions` | 查询余额流水（分页） | 登录用户 |
| `GET` | `/api/v1/billing/topup-orders` | 查询充值记录（分页） | 登录用户 |
| `GET` | `/api/v1/billing/usage` | 查询用量统计（支持按模型/key/时段过滤） | 登录用户 |
| `GET` | `/api/v1/billing/usage/logs` | 查询调用明细日志（分页） | 登录用户 |
| `GET` | `/api/v1/keys` | 列出我的 API Key | 登录用户 |
| `POST` | `/api/v1/keys` | 创建 API Key | 登录用户 |
| `PATCH` | `/api/v1/keys/{key_id}` | 修改 Key（名称/配额/模型限制） | 登录用户 |
| `POST` | `/api/v1/keys/{key_id}/disable` | 禁用 Key | 登录用户 |
| `DELETE` | `/api/v1/keys/{key_id}` | 删除 Key | 登录用户 |

**响应注意事项：**
- `GET /billing/usage/logs` 返回的 `api_call_logs` 中，`cost_detail` 字段对普通用户**不返回**（service 层在组装响应时裁掉该字段）
- `GET /billing/balance` 只返回 `balance` 和 `used_amount`，不返回 `frozen_amount`（内部字段）

### 6.2 管理员端（`/api/v1/admin/` 系列，需 admin 权限）

| 方法 | 路径 | 功能 |
|---|---|---|
| `POST` | `/api/v1/admin/users/{uid}/topup` | 手动充值 |
| `POST` | `/api/v1/admin/users/{uid}/adjust-balance` | 调整余额（增减） |
| `GET` | `/api/v1/admin/topup-orders` | 查询所有充值记录 |
| `GET` | `/api/v1/admin/users/{uid}/transactions` | 查询指定用户流水 |
| `GET` | `/api/v1/admin/usage/logs` | 查询全局调用日志（含 cost_detail） |
| `GET` | `/api/v1/admin/usage/stats` | 查询全局用量统计 |
| `DELETE` | `/api/v1/admin/usage/logs/history` | 清理指定日期前的历史日志 |

### 6.3 内部 HMAC 端点（`/api/v1/internal/`，供 router-service 调用）

> 调用方：`router-service`，鉴权方式：HMAC 签名（与现有内部接口一致）

| 方法 | 路径 | 功能 |
|---|---|---|
| `POST` | `/internal/billing/freeze` | 预冻结余额 |
| `POST` | `/internal/billing/settle` | 结算（解冻 + 扣费 + 写 api_call_log） |
| `POST` | `/internal/billing/refund` | 失败退款（解冻） |
| `GET` | `/internal/api-keys/{key_hash}` | 校验 key 有效性，返回配额状态 |
| `POST` | `/internal/api-keys/{key_hash}/consume` | 更新 key.quota_used（结算时调用） |

**`POST /internal/billing/freeze` 请求体：**
```json
{
  "user_id": 123456789,
  "api_key_hash": "abc...",
  "request_id": "req_xxx",
  "estimated_amount": 15
}
```

**`POST /internal/billing/settle` 请求体：**
```json
{
  "user_id": 123456789,
  "api_key_hash": "abc...",
  "request_id": "req_xxx",
  "estimated_amount": 15,
  "actual_amount": 12,
  "model_name": "gpt-4o",
  "prompt_tokens": 500,
  "completion_tokens": 200,
  "cached_tokens": 0,
  "total_tokens": 700,
  "duration_ms": 1240,
  "is_stream": false,
  "ip": "1.2.3.4",
  "cost_detail": {
    "input_unit_price": 10,
    "output_unit_price": 30,
    "cache_unit_price": 2,
    "input_cost": 5,
    "output_cost": 6,
    "cache_cost": 0,
    "markup_rate": 1.2
  }
}
```

---

## 七、router-service 新增职责

> 以下为 router-service 需要实现的计费流程，user-service 提供对应的 HMAC 接口支持。

### 7.1 三段式计费流程

```
用户请求到达 router-service
│
├─ 1. 校验 API Key
│     GET /internal/api-keys/{key_hash}
│     → 获取 user_id / quota_mode / remaining_quota / status
│     → key exhausted / expired / disabled → 拒绝，返回对应错误
│
├─ 2. 估算 token 费用
│     根据模型单价 × 估算 token 数 → estimated_amount（分）
│
├─ 3. 预冻结
│     POST /internal/billing/freeze
│     → 余额不足 → 拒绝，返回 "余额不足" 错误
│     → key mode=2 且 remaining_quota < estimated_amount → 拒绝，返回 "key 额度不足"
│
├─ 4. 调用上游 LLM
│
├─ 5A. 调用成功 → 结算
│      POST /internal/billing/settle
│      （携带完整 cost_detail）
│
└─ 5B. 调用失败 → 退款
       POST /internal/billing/refund
```

### 7.2 注意事项

- `request_id` 由 router-service 生成，格式建议：`req_{snowflake_id}`，全局唯一
- freeze / settle / refund 均为幂等接口，router 可以安全重试
- settle 接口在 user-service 内部原子完成：写 `api_call_logs` + 更新 `users` 余额字段 + 更新 `key.quota_used` 全部在同一事务
- cost_detail 由 router-service 计算后随 settle 一起传入，user-service 不负责定价逻辑

---

## 八、arq 定时任务新增

在现有 arq worker 中新增以下任务：

### 8.1 用量统计聚合任务

```python
# 任务名：aggregate_usage_stats
# 执行频率：每小时执行一次（cron: 0 * * * *）
# 逻辑：
#   1. 计算上一个整点小时（如当前 15:23，则聚合 14:00 的数据）
#   2. 调用 UsageStatService.aggregate_hour(stat_hour)
#   3. 记录执行日志（聚合了多少行，耗时多少）
```

### 8.2 邀请码释放补偿任务

```python
# 任务名：retry_invitation_release_outbox
# 执行频率：每 5 分钟（cron: */5 * * * *）
# 逻辑：
#   1. 查询 invitation_release_outbox WHERE retry_count < 5
#   2. 对每条记录调用 admin_client.release_invitation_code(code, used_by_uid)
#   3. 成功 → 删除该记录
#   4. 失败 → retry_count += 1，last_error = 错误信息，指数退避
#   5. retry_count >= 5 → 发告警日志，等待人工处理
```

### 8.3 验证码 TTL 清理任务

```python
# 任务名：cleanup_expired_verification_codes
# 执行频率：每天凌晨 3:00（cron: 0 3 * * *）
# 逻辑：
#   DELETE FROM email_verification_codes
#   WHERE expires_at < NOW() - INTERVAL 7 DAY
#     AND used_at IS NOT NULL
# 利用现有的 idx_codes_expires_at 索引
```

---

## 九、配置项变更

### 9.1 新增配置项（`config.py`）

```python
class Settings(BaseServiceSettings):
    # 余额相关
    MIN_TOPUP_AMOUNT:    int = 100    # 最低充值金额（分），默认 ¥1
    MAX_TOPUP_AMOUNT:    int = 1000000  # 最高单次充值金额（分），默认 ¥10000

    # API Key 相关
    MAX_API_KEYS_PER_USER: int = 20   # 每用户最多创建多少个 key

    # 硬编码魔数迁移（原先散落在 auth_service / email_service）
    LOGIN_MAX_FAILURES:        int = 5
    LOGIN_LOCK_DURATION_HOURS: int = 1
    MAX_CODE_ERRORS:           int = 5
    CODE_ERROR_LOCK_HOURS:     int = 24
    CODE_DAILY_SEND_LIMIT:     int = 3
```

### 9.2 删除配置项

- `CONTENT_SERVICE_URL`（standalone 清理）
- `ROUTER_SERVICE_URL`（孤岛代码清理）

---

## 十、执行顺序建议

建议按以下顺序执行，每步完成后运行全量测试再继续：

```
阶段 1 - 清理（无功能变化，最低风险）
  1.1 删除 user_active_sessions 僵尸表及相关代码
  1.2 删除 standalone 部署相关代码
  1.3 删除 RouterApiKey 孤岛 schemas
  1.4 清理未使用的 Depends 函数
  1.5 清理 by-id 内部接口（或补充注释）

阶段 2 - 数据库扩展（需停机迁移或在线 DDL）
  2.1 users 表新增余额字段（ALTER TABLE，有默认值，安全）
  2.2 新建 user_api_keys 表
  2.3 新建 balance_transactions 表
  2.4 新建 topup_orders 表
  2.5 新建 api_call_logs 表
  2.6 新建 usage_stats 表
  2.7 新建 invitation_release_outbox 表

阶段 3 - Model & Service（后端逻辑）
  3.1 新增 ORM models
  3.2 新增 BalanceService / ApiKeyService / TopupOrderService
  3.3 修改注册流程（验证码延迟消费 + outbox 兜底）
  3.4 魔数迁移到 config.py

阶段 4 - 端点与接口
  4.1 新增用户端计费/key 端点
  4.2 新增管理员端端点
  4.3 新增 router-service 调用的内部 HMAC 端点

阶段 5 - 定时任务
  5.1 用量统计聚合任务
  5.2 邀请码释放补偿任务
  5.3 验证码 TTL 清理任务
```

---

## 十一、不在本次重构范围内

以下内容明确**不处理**，留待后续决策：

- 支付宝 / 微信 / Stripe 支付接入（`topup_orders` 表已预留字段）
- 多设备会话支持（当前单活跃会话策略不变）
- email 规范化 validator 验证（需确认 Pydantic schema 层是否已处理）
- `usage_stats` 数据归档策略（数据量大后的冷热分离方案）