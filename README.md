# Eucal AI 后端部署手册

本文档面向第一次部署和后续维护人员，重点回答 4 件事：

1. 正式部署时先做什么、后做什么
2. `.env` 里的每一项配置分别是什么意思
3. 超级管理员应该如何初始化
4. 数据库能不能通过命令一键创建

最短结论：

1. 先安装依赖并准备 `.env`
2. 手动创建 3 个 MySQL 数据库（router 已改为无 DB 的 ML 推理服务）
3. 运行 `uv run check-env`
4. 运行数据库迁移（创建数据表）
5. 初始化超级管理员
6. 再启动全部后端服务

## 架构概览

当前后端是单仓库、多服务架构，全部包位于 `src/` 下：

| 服务 | 模块 | 默认端口 | 作用 |
| --- | --- | --- | --- |
| `backend-app` | `src/backend_app/` | `8001` | admin + user + testing 合并控制面 |
| `user-service` | `src/user_service/` | `8000` | 用户注册、登录、密码（独立进程可选） |
| `admin-service` | `src/admin_service/` | `8001` | 管理员登录、超级管理员、邀请码、审计（独立进程可选） |
| `testing-service` | `src/testing_service/` | `8002` | 模型目录、供应商、报价、Benchmark（独立进程可选） |
| `router-service` | `src/router_service/` | `8003` | ML 推理路由（无数据库） |
| `testing-worker` | `testing_service.worker` | 无 HTTP 端口 | 执行 Benchmark 队列任务 |
| `testing-scheduler` | `testing_service.main:app` | `8012` | 定时探测调度入口 |

说明：

- `src/common/` 只提供公共基础设施能力，例如 JWT、配置、日志、数据库运行时、内部服务签名
- 服务之间通过内部 HTTP API 通信，不应跨服务直接导入业务模块
- **router-service** 现为独立的 ML 推理服务，仅负责路由决策，不再承载 Router Key、用量统计、计费与 OpenAI 兼容代理。旧 router key/billing 链路已从代码与测试中暂时下线。
- 安装 router 依赖需要 `uv sync --extra router`（包含 torch/transformers/numpy 等 ML 包）。

## 正式部署顺序

建议严格按下面顺序执行：

1. 准备 Python、MySQL、Redis
2. 执行 `uv sync`
3. 复制 `.env.example` 为 `.env`
4. 修改 `.env`
5. 手动创建 MySQL 数据库和账号权限
6. 运行 `uv run check-env`
7. 运行数据库迁移
8. 初始化超级管理员
9. 校验超级管理员已存在
10. 启动全部服务
11. 验证 `/ready`、管理员登录、内部链路和 worker

不要把“初始化超级管理员”放到服务启动之后再补做。`admin-service` 启动时会校验是否存在活跃 `super_admin`。

## 运行前提

### 必需软件

- Python `3.10+`
- [uv](https://docs.astral.sh/uv/)
- MySQL `8.x`
- Redis `7.x`

### 可选软件

如果使用容器部署，还需要：

- Docker
- Docker Compose

## 安装依赖

在 [backend](/F:/Eucal_AI/backend) 目录执行：

```bash
uv sync
```

## 第一步：复制并编辑 `.env`

复制模板：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

下面这张表解释 `.env.example` 里各个配置项的含义。

## 环境变量说明

### 基础信息

| 变量 | 是否必填 | 作用范围 | 含义 | 典型值 |
| --- | --- | --- | --- | --- |
| `PROJECT_NAME` | 否 | 全局 | 项目显示名称，主要用于文档或日志展示 | `Eucal AI API` |
| `DEBUG` | 建议必填 | 全局 | 是否开启调试模式；为 `true` 时会开放 `/docs` 等调试能力 | `true` / `false` |
| `ALLOWED_HOSTS` | 建议必填 | 多数 HTTP 服务 | CORS 允许来源列表，支持逗号分隔 | `http://localhost:3000,http://localhost:3001` |
| `CONTACT_EMAIL_TO` | 否 | 当前不是启动硬依赖 | 联系邮箱占位配置，可按业务保留 | `contact@eucal.ai` |

### SMTP 邮件配置

这些变量主要给 `user-service` 的邮箱验证码能力使用。

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `SMTP_HOST` | 需要发邮件时必填 | `user-service` | SMTP 服务器地址 |
| `SMTP_PORT` | 需要发邮件时建议填 | `user-service` | SMTP 端口，常见 `587` |
| `SMTP_USER` | 需要发邮件时必填 | `user-service` | SMTP 登录用户名 |
| `SMTP_PASSWORD` | 需要发邮件时必填 | `user-service` | SMTP 登录密码或授权码 |
| `SMTP_TLS` | 需要发邮件时建议填 | `user-service` | 是否启用 TLS |

如果你暂时不用邮箱验证码功能，这组配置可以先不填。

### 安全和认证

| 变量 | 是否必填 | 作用范围 | 含义 | 备注 |
| --- | --- | --- | --- | --- |
| `JWT_SECRET_KEY` | 是 | 全局 | JWT 签名密钥 | 长度必须至少 32 位 |
| `JWT_ALGORITHM` | 建议填 | 全局 | JWT 签名算法 | 当前默认 `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 建议填 | `user-service`、`admin-service` | access token 过期时间，单位分钟 | |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 建议填 | 主要影响用户刷新令牌 | refresh token 过期时间，单位天 | |
| `INTERNAL_SECRET` | 是 | 全局 | 微服务内部请求签名共享密钥 | 不一致会导致内部调用失败 |
| `COOKIE_SECURE` | 建议填 | `user-service`、`admin-service` | cookie 是否只允许 HTTPS 发送 | 生产必须 `true` |
| `COOKIE_SAMESITE` | 建议填 | `user-service`、`admin-service` | cookie SameSite 策略 | 常见 `lax` |

### 数据库配置

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `ADMIN_DATABASE_URL` | 是 | `admin-service` | 管理员域数据库连接串 |
| `USER_DATABASE_URL` | 是 | `user-service` | 用户域数据库连接串 |
| `TESTING_DATABASE_URL` | 是 | `testing-service`、`testing-worker`、`testing-scheduler` | 模型与 Benchmark 域数据库连接串 |
| `DATABASE_POOL_SIZE` | 建议填 | 全局 | 数据库连接池基础连接数 |
| `DATABASE_MAX_OVERFLOW` | 建议填 | 全局 | 连接池允许的额外溢出连接数 |
| `DATABASE_ECHO` | 否 | 全局 | 是否打印 SQL 日志 | 调试时可设 `true` |

### 服务地址配置

这些变量决定服务之间如何互相访问。

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `ADMIN_SERVICE_URL` | 建议填 | 被 `user-service`、`testing-service` 使用 | `admin-service` 的访问地址 |
| `USER_SERVICE_URL` | 建议填 | 被 `admin-service`、`router-service` 使用 | `user-service` 的访问地址 |
| `ROUTER_SERVICE_URL` | 建议填 | 用户链路或其他调用链使用 | `router-service` 的访问地址 |
| `TESTING_SERVICE_URL` | 建议填 | `router-service` 使用 | `testing-service` 的访问地址 |

如果是本机部署，通常写 `http://localhost:端口`。如果是 Docker Compose，应写成容器内服务名地址。

### Snowflake ID 配置

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `SNOWFLAKE_WORKER_ID` | 建议填 | 全局 | 雪花 ID 生成器的 worker 编号 |
| `SNOWFLAKE_DATACENTER_ID` | 建议填 | 全局 | 雪花 ID 生成器的数据中心编号 |

单机环境可保持默认。多实例生产环境应统一规划，避免生成重复 ID。

### Testing / Benchmark / 队列配置

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `BENCHMARK_QUEUE_REDIS_URL` | 启用 testing 相关任务时必填 | `testing-service`、`testing-worker`、`testing-scheduler` | Benchmark 队列 Redis 地址 |
| `BENCHMARK_WORKER_CONCURRENCY` | 建议填 | `testing-worker` | worker 并发数 |
| `PROBE_ENABLED` | 建议填 | `testing-service` | 是否允许探测与 benchmark 链路 |
| `PROBE_SCHEDULER_ENABLED` | 建议填 | `testing-service` / `testing-scheduler` | 是否启用定时调度 |
| `PROBE_CRON_HOURS` | 建议填 | `testing-scheduler` | 每天哪些小时执行定时探测，逗号分隔 |
| `TESTING_SECRET_MASTER_KEY` | 建议填 | `testing-service` | 用于加密/解密 provider 探测密钥 |

说明：

- `testing-worker` 负责真正执行队列任务
- `testing-scheduler` 负责定时把任务推入队列
- Redis 不可用时，`testing-worker` 和 `testing-scheduler` 都会有问题

### Router 配置

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `ROUTER_SECRET_MASTER_KEY` | 建议填 | `router-service` | router 自身敏感数据的主密钥 |
| `PROVIDER_SECRET_MASTER_KEY` | 建议填 | `router-service` | provider 凭据相关主密钥 |
| `SMART_ROUTER_ENABLED` | 否 | `router-service` | 是否开启 smart router |
| `SMART_ROUTER_ALIAS` | smart router 开启时必填 | `router-service` | smart router 虚拟模型别名 |
| `SMART_ROUTER_DIFFICULTY_MODEL_MAP` | smart router 开启时建议填 | `router-service` | 难度到模型的映射，例如 `1:model-a,3:model-b,5:model-c` |
| `SMART_ROUTER_FALLBACK_MODEL` | smart router 开启时建议填 | `router-service` | 无法分类或没有候选时的回退模型 |

如果你暂时不用 smart router，可以保持关闭。

### 超级管理员引导配置

| 变量 | 是否必填 | 作用范围 | 含义 |
| --- | --- | --- | --- |
| `BOOTSTRAP_SUPERADMIN_ENABLED` | 首次部署时建议开启 | `admin-service` | 是否允许系统根据环境变量创建或更新初始超级管理员 |
| `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP` | 建议保持 `true` | `admin-service` | 如果不存在活跃超级管理员，启动时是否直接报错 |
| `BOOTSTRAP_SUPERADMIN_EMAIL` | 首次部署时必填 | `admin-service` | 初始超级管理员邮箱 |
| `BOOTSTRAP_SUPERADMIN_PASSWORD` | 首次部署时必填 | `admin-service` | 初始超级管理员密码 |
| `BOOTSTRAP_SUPERADMIN_NAME` | 首次部署时必填 | `admin-service` | 初始超级管理员显示名 |
| `BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS` | 特殊场景使用 | `admin-service` | 如果该超级管理员已存在，是否强制重置密码 |
| `BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS` | 特殊场景使用 | `admin-service` | 如果该超级管理员已存在，是否同步更新名称 |

推荐策略：

- 首次部署时：`BOOTSTRAP_SUPERADMIN_ENABLED=true`
- 初始化完成后：改回 `BOOTSTRAP_SUPERADMIN_ENABLED=false`
- 长期保持 `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=true`

## 第二步：手动创建数据库

### 当前仓库能否一键创建数据库

不能。

当前命令：

- `uv run bootstrap-databases`
- `uv run migrate --service ... upgrade head`

都只能在数据库已经存在的前提下运行迁移，不会自动：

- `CREATE DATABASE`
- 创建数据库用户
- 分配数据库权限

因此第一次部署时必须先手动建库。

### 推荐数据库名

- `eucal_ai_admin`
- `eucal_ai_user`
- `eucal_ai_testing`

### 创建数据库示例

```sql
CREATE DATABASE eucal_ai_admin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE eucal_ai_user CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE eucal_ai_testing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

如需独立业务账号授权：

```sql
GRANT ALL PRIVILEGES ON eucal_ai_admin.* TO 'eucal'@'%';
GRANT ALL PRIVILEGES ON eucal_ai_user.* TO 'eucal'@'%';
GRANT ALL PRIVILEGES ON eucal_ai_testing.* TO 'eucal'@'%';
FLUSH PRIVILEGES;
```

如果你没有 `CREATE DATABASE` 权限，就必须让 DBA 先建好这些数据库并授权。

## 第三步：运行环境预检查

在 [backend](/F:/Eucal_AI/backend) 目录执行：

```bash
uv run check-env
```

该命令会检查：

- `JWT_SECRET_KEY` 是否缺失、过短或仍是占位值
- `INTERNAL_SECRET` 是否缺失
- 目标服务需要的 `*_DATABASE_URL` 是否存在
- `testing-worker` / `testing-scheduler` 是否缺 Redis
- 是否存在高风险回退配置

如果这里失败，不要跳过，先把 `.env` 修好。

## 第四步：执行数据库迁移

### 推荐方式

第一次部署时，建议显式逐个执行：

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run migrate --service testing-service upgrade head
```

### 批量方式

也可以使用：

```bash
uv run bootstrap-databases
```

或只迁移部分服务：

```bash
uv run bootstrap-databases admin-service user-service
```

### 这一步实际做了什么

- 读取 `.env` 中各服务数据库连接串
- 调用 Alembic 迁移
- 将 schema 升级到最新版本

### 这一步不会做什么

- 不会创建数据库本身
- 不会创建数据库账号
- 不会自动修复错误的数据库地址

### SQL 快照说明

[scripts/sql](/F:/Eucal_AI/backend/scripts/sql) 下有服务级 schema 快照，可用于核对初始结构，但正式部署仍应以迁移为准。

## 第五步：初始化超级管理员

### 为什么必须在启动前做

`admin-service` 启动时会检查是否存在活跃 `super_admin`。

实际逻辑是：

1. 如果已有活跃 `super_admin`，启动继续
2. 如果没有活跃 `super_admin` 且 `BOOTSTRAP_SUPERADMIN_ENABLED=true`，服务会尝试按环境变量创建
3. 如果没有活跃 `super_admin` 且 `BOOTSTRAP_SUPERADMIN_ENABLED=false`，并且 `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=true`，启动直接失败

所以第一次部署时，正确做法是先跑迁移，再显式执行 bootstrap 命令。

### 首次部署推荐配置

```env
BOOTSTRAP_SUPERADMIN_ENABLED=true
BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=true
BOOTSTRAP_SUPERADMIN_EMAIL=founder@example.com
BOOTSTRAP_SUPERADMIN_PASSWORD=StrongPassword123!
BOOTSTRAP_SUPERADMIN_NAME=System Founder
BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=false
BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS=false
```

### 初始化命令

先执行 `admin-service` 的迁移，再执行：

```bash
uv run bootstrap-super-admin
```

然后做存在性检查：

```bash
uv run bootstrap-super-admin --check-only
```

`bootstrap-super-admin` 不再承担 schema 初始化职责。必须先执行 Alembic 迁移，再运行该命令。

### 初始化成功后应该做什么

建议立刻完成这些动作：

1. 用超级管理员账号登录管理端
2. 确认能进入后台
3. 创建至少一个邀请码
4. 检查管理员链路和审计日志是否正常
5. 把 `.env` 里的 bootstrap 开关改回安全状态

推荐改成：

```env
BOOTSTRAP_SUPERADMIN_ENABLED=false
BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=true
BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=false
BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS=false
```

这样做的效果是：

- 系统启动时仍然强制要求存在至少一个活跃超级管理员
- 但不会在每次启动时继续根据环境变量修改账号

### 如果要重置初始超级管理员密码

只在一次性操作时临时打开：

```env
BOOTSTRAP_SUPERADMIN_ENABLED=true
BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=true
```

重置完成后立即改回去。

## 第六步：启动服务

### 本地或测试环境

默认启动所有服务：

```bash
uv run start
```

当前默认会启动：

- `admin-service`
- `user-service`
- `testing-service`
- `router-service`
- `testing-worker`
- `testing-scheduler`

开发模式：

```bash
uv run start --dev
```

只启动部分服务：

```bash
uv run start admin-service user-service
```

只单独启动定时探测调度器：

```bash
uv run start testing-scheduler
```

说明：

- `uv run start` 会先执行与 `check-env` 一致的预检查
- `testing-service` 和 `testing-scheduler` 会带不同的 `PROBE_SCHEDULER_ENABLED` 运行时覆盖
- 除非你明确知道自己在做什么，否则不要使用 `--skip-preflight`

### Docker Compose

容器部署：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

如果你要显式启动 scheduler profile：

```bash
docker compose -f deploy/docker-compose.yml --profile scheduler up -d testing-scheduler
```

如果你希望容器默认启动策略与 `uv run start` 完全一致，应额外核对 Compose 默认 profile 是否也包含 scheduler。

## 第七步：部署后验证

### HTTP 就绪检查

```bash
curl http://localhost:8000/ready
curl http://localhost:8001/ready
curl http://localhost:8002/ready
curl http://localhost:8003/ready
curl http://localhost:8012/ready
```

### Worker 检查

```bash
uv run python scripts/runtime_probe.py worker-ready --database-url-env TESTING_DATABASE_URL --redis-url-env BENCHMARK_QUEUE_REDIS_URL
```

### 管理员链路检查

至少验证：

1. 用超级管理员账号登录管理端
2. 查看当前管理员信息
3. 创建一条邀请码
4. 检查审计日志是否记录成功

### OpenAPI 文档

当 `DEBUG=true` 时，各 HTTP 服务可访问 `/docs`：

- [http://localhost:8000/docs](http://localhost:8000/docs)
- [http://localhost:8001/docs](http://localhost:8001/docs)
- [http://localhost:8002/docs](http://localhost:8002/docs)
- [http://localhost:8003/docs](http://localhost:8003/docs)
- [http://localhost:8012/docs](http://localhost:8012/docs)

## 服务间调用约定

内部调用统一依赖签名请求头：

- `X-Request-ID`
- `X-Internal-Service`
- `X-Internal-Timestamp`
- `X-Internal-Signature`

当前主要依赖关系：

- `admin-service -> user-service`：用户统计、用户身份查询
- `user-service -> admin-service`：邀请码消费与释放
- `router-service -> user-service`：Router Key 所属用户校验
- `router-service -> testing-service`：模型目录与路由候选查询
- `testing-service -> admin-service`：管理员身份校验

如果 `INTERNAL_SECRET` 不一致，内部调用会失败。

## 常见问题

### 1. `uv run check-env` 失败

通常是：

- 缺少某个 `*_DATABASE_URL`
- `JWT_SECRET_KEY` 长度不足 32 位
- `JWT_SECRET_KEY` 仍然是占位值
- `INTERNAL_SECRET` 未配置
- `testing` 相关角色缺 Redis

### 2. 迁移时报数据库不存在

说明数据库还没手动创建，或者 `.env` 中数据库名写错了。

### 3. `admin-service` 启动时报没有 `super_admin`

说明数据库里没有活跃超级管理员，且 bootstrap 没有正确执行。按下面顺序处理：

```bash
uv run migrate --service admin-service upgrade head
uv run bootstrap-super-admin
uv run bootstrap-super-admin --check-only
```

### 4. `testing-worker` 或 `testing-scheduler` 起不来

优先检查：

- `TESTING_DATABASE_URL`
- `BENCHMARK_QUEUE_REDIS_URL`
- Redis 是否可访问
- `PROBE_ENABLED` 与 `PROBE_SCHEDULER_ENABLED` 是否符合预期

### 5. `/ready` 返回 `503`

优先检查：

- 数据库是否可达
- Redis 是否可达
- 迁移是否已经执行到最新
- 目标服务依赖的下游服务是否已启动

### 6. 服务间调用返回 `503`

优先检查：

- 目标服务是否已经 `ready`
- `INTERNAL_SECRET` 是否一致
- `*_SERVICE_URL` 是否配置正确

## 生产建议

- 每个服务使用独立数据库
- 生产环境启用 `COOKIE_SECURE=true`
- `JWT_SECRET_KEY`、`INTERNAL_SECRET`、各类 `*_MASTER_KEY` 使用强随机值
- 不要把 `testing-worker` 和 `testing-scheduler` 暴露到公网
- `/ready` 用于健康检查，`/health` 用于进程存活
- 初始超级管理员密码不要长期以明文保存在 `.env`

## Phase 4 Status

运行时观测与契约（详见 `docs/phase4-operations.md` 和 `docs/service-runtime-contracts.md`）：

- 每个请求带 `X-Request-ID` 贯穿（`common/observability.REQUEST_ID_HEADER`），响应回写、跨服务透传、日志串联
- 服务间调用是 signed internal HMAC（`common/internal.py`），带断路器与重试
- 数据库快照在 `scripts/sql/` 下（`admin_schema.sql`、`user_schema.sql` 等），由 `mysqldump` 重新生成；**Alembic 是 schema 真理**，见 `migrations/README.md`
- phase2 切换工具：`docs/phase2-cutover.md`
