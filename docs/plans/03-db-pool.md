# Plan 03 — DB 池补全 `pool_recycle` / `pool_timeout`

> 优先级：🔥🔥
> 性质：鲁棒性
> 影响面：admin-service 与 user-service 各自的 `common/db/runtime.py:21-38`
> 预计工作量：0.5 人日（含验证）
> 风险：极低（参数补全，行为只在边界情况下改变）

---

## 1. 现状

### 1.1 当前 engine 配置

`services/admin-service/src/common/db/runtime.py:21-38`（user-service 同步）：
```python
def create_engine(
    self,
    database_url: str,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
) -> AsyncEngine:
    self._engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
    )
```

`.env`：
```
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

调用方：
- `services/admin-service/src/main.py:45-50`（lifespan）
- `services/admin-service/src/core/bootstrap_superadmin.py:38-41`（CLI bootstrap）
- user-service 类似

### 1.2 缺失参数的后果

#### 缺 `pool_recycle`
- MySQL 服务端默认 `wait_timeout = 28800s (8h)`，连接长时间空闲会被服务端**单方面**关闭
- SQLAlchemy 池里的连接不知道这件事，下次拿出来用会直接抛 `MySQLdb.OperationalError: (2006, 'MySQL server has gone away')` 或 `(2013, 'Lost connection')`
- 当前依赖 `pool_pre_ping=True` 兜底——每次拿连接前先 `SELECT 1`，**有效但每次拿连接多一次 RTT**（生产 ~0.3-0.8ms）
- 设了 `pool_recycle=1800`（30 分钟）后，连接到龄即被回收，远小于 wait_timeout，pre_ping 大部分情况下不会真正触发，省去往返开销

#### 缺 `pool_timeout`
- 默认 SQLAlchemy `pool_timeout=30s`——拿不到连接时的等待时长
- 30s 在 FastAPI 的请求路径上**太长**：
  - 上游 gateway 早就超时返回 502
  - 但请求在 worker 内部依然挂着等连接
  - 表现为"客户端见到 502 但服务端 worker 仍占用"，制造幽灵流量
- 设小一点（10s 或更短）让连接池争抢失败时**快速失败**而非排队

### 1.3 为什么是 🔥🔥

- 单点故障类型：MySQL 重启 / 网络分区恢复后，所有空闲连接都失效，pre_ping 单兵作战会有 N 次失败 → 重连风暴
- 长尾延迟类型：连接池满时整个请求 hang 30s，用户看到 504 但日志看不出原因
- 改动只在两个文件，参数补全，**没有任何代码语义变更**

---

## 2. 目标

1. 在 `ServiceDatabaseRuntime.create_engine` 增加两个参数：`pool_recycle` 与 `pool_timeout`
2. 配置项接入 `.env` 与 `Settings`，提供合理默认值
3. 调用点更新（admin/user 的 `main.py` 与 bootstrap 脚本）
4. 单元测试 + 手工验证 wait_timeout 场景

---

## 3. 设计

### 3.1 参数与默认值

| 参数 | 默认值 | 选取理由 |
|---|---|---|
| `pool_recycle` | `1800`（秒，30 分钟） | 远小于 MySQL `wait_timeout=28800`；30 分钟内一次回收，对长连接业务零感知；与多数云数据库（RDS/PolarDB）默认 wait_timeout 也兼容 |
| `pool_timeout` | `10`（秒） | 大于业务 SLA 抓取尾延迟（通常 1-3s），小于上游 gateway 超时（典型 30s）；配合 max_overflow=20 已足以应对突发 |

可调，通过 env 暴露。

### 3.2 代码改动

#### 3.2.1 `common/db/runtime.py`（admin/user 各一份）

```python
def create_engine(
    self,
    database_url: str,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_recycle: int = 1800,     # ← 新增
    pool_timeout: int = 10,       # ← 新增
) -> AsyncEngine:
    """Create and cache an async engine for this service."""
    self._engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=pool_recycle,   # ← 新增
        pool_timeout=pool_timeout,   # ← 新增
    )
    if self._engine.sync_engine.dialect.name == "mysql":
        event.listen(self._engine.sync_engine, "connect", self._set_mysql_time_zone)
    return self._engine
```

#### 3.2.2 `common/config.py`（admin/user 各一份）

```python
class Settings(BaseSettings):
    ...
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800   # ← 新增
    DATABASE_POOL_TIMEOUT_SECONDS: int = 10     # ← 新增
```

#### 3.2.3 `main.py` lifespan 调用点

```python
# services/admin-service/src/main.py:45-50
create_engine(
    database_url=settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,   # ← 新增
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,   # ← 新增
    echo=settings.DATABASE_ECHO,
)
```

`bootstrap_superadmin.py:38-41` 同步更新。user-service 同步。

#### 3.2.4 `.env` / `.env.example`

```
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_RECYCLE_SECONDS=1800   # ← 新增
DATABASE_POOL_TIMEOUT_SECONDS=10     # ← 新增
```

---

## 4. 改造步骤

可作单个 commit 完成，但建议分两个 commit 便于回滚：

### Step 1：admin-service 改造
1. `common/db/runtime.py:21-38` 加参数
2. `common/config.py` 加 Settings 字段
3. `main.py:45-50` 传参
4. `core/bootstrap_superadmin.py:38-41` 传参
5. `.env` / `.env.example` 加默认值
6. 跑现有单测确认无回归

### Step 2：user-service 改造
- 同 Step 1 在 user-service 重复一遍

> 是否抽象到共享层？当前 `common/db/runtime.py` 是 vendored copy（admin 与 user 各持一份），抽象到 monorepo 共享层是另一个工程项，不在本轮范围。

---

## 5. 验证方案

### 5.1 单元测试

`tests/test_db_runtime.py`（如已有则 augment，无则新增）：
- 验证 `create_engine` 接受新参数且不抛
- 验证传入无效值（如负数）的行为符合 SQLAlchemy 约定

### 5.2 集成验证 — wait_timeout 模拟

本地 MySQL 临时设短 wait_timeout：
```sql
SET GLOBAL wait_timeout = 60;
SET GLOBAL interactive_timeout = 60;
```

启动 admin-service：
- **改造前**：等待 70s 后访问任意 DB 接口，期望首次报错（`MySQL server has gone away`）或 pre_ping 触发重连导致额外延迟
- **改造后** `pool_recycle=30`（测试值，配合 wait_timeout=60）：所有连接每 30s 自动回收，70s 后访问无异常、无 pre_ping 触发

### 5.3 集成验证 — pool_timeout 模拟

设 `pool_size=2, max_overflow=0, pool_timeout=2`，并发打 5 个长事务请求：
- 期望：前 2 个正常；后 3 个等 2s 后抛 `TimeoutError: QueuePool limit ... reached`
- 当前默认（pool_timeout=30）：后 3 个等 30s——验证现有问题确实存在

### 5.4 生产观测点

接入 Prometheus 后（下一轮）需观察：
- `db_pool_connections_in_use`
- `db_pool_overflow`
- `db_pool_wait_seconds_p99`
- 连接 reset 频次

本轮先在日志层加：
```python
# 在 common/db/runtime.py close_db 或定期心跳处
logger.info("db_pool_status", in_use=engine.pool.checkedout(), size=engine.pool.size(), overflow=engine.pool.overflow())
```

---

## 6. 回滚方案

- 改动是纯参数补全，**SQLAlchemy 无新参数时使用其内置默认值**——回滚 = 删两行参数 + 删两个 Settings 字段 + 还原 `.env`
- `pool_recycle` / `pool_timeout` 是 SQLAlchemy 1.4+ 标准参数，不引入新依赖
- 若线上压测发现 `pool_timeout=10` 偏严，可单独调 `.env` 不需重发版

---

## 7. 风险与陷阱

| 风险 | 应对 |
|---|---|
| `pool_recycle=1800` 低于业务长事务持续时间 | 检查现有 long-running query；若有 30 分钟以上事务（一般是异步任务），需要单独 session 走非池路径（`NullPool`），但当前看 admin/user 都是 OLTP 短事务，安全 |
| 生产 MySQL `wait_timeout` 配置未知 | 部署前用 `SHOW VARIABLES LIKE 'wait_timeout'` 确认；若小于 1800 需调小 pool_recycle |
| `pool_timeout=10` 在大流量下挤爆池 | 观测 `pool_overflow` 指标；不够时**先扩 pool_size 与 max_overflow**，而非放宽 timeout（治本不治标） |
| `pool_pre_ping=True` 与 `pool_recycle` 是否冗余？ | 不冗余：pool_recycle 是基于"连接年龄"，pool_pre_ping 是基于"使用前探测"。两者一起用更稳：recycle 大幅减少 ping 触发，ping 兜底意外断连（如网络抖动）。建议保留 pre_ping |
| 现有 `bootstrap_superadmin.py` 是一次性脚本是否需要传参？ | 是；不传等于走代码默认值（与 main.py 行为一致），但保持一致更好 |

---

## 8. Definition of Done

- [ ] `services/admin-service/src/common/db/runtime.py` 加 `pool_recycle`/`pool_timeout` 参数
- [ ] `services/user-service/src/common/db/runtime.py` 同步
- [ ] `services/admin-service/src/common/config.py` Settings 字段
- [ ] `services/user-service/src/common/config.py` 同步
- [ ] admin/user `main.py` 与 bootstrap 脚本传参更新
- [ ] `.env` / `.env.example` 两个服务都加新键
- [ ] 现有单测全绿
- [ ] 本地 wait_timeout 场景验证通过（改造后 70s 后无异常）
- [ ] 本地 pool_timeout 场景验证通过（改造后 2s 内快速失败）

---

## 9. 与其他改造的依赖关系

- 与 Plan 01（httpx 单例化）独立，无依赖
- 与 Plan 02（CB 搬 Redis）独立，无依赖
- 三项可并行推进；建议**先做本计划**——改动量最小、风险最低，先建立改造节奏感
