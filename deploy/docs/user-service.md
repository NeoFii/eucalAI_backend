# user-service 部署

## 概述

user-service 是面向终端用户的核心业务服务，负责用户认证、账单管理、API Key 管理、调用日志、代金券兑换和模型目录网关（缓存代理 admin-service 数据）。

- 端口：8000
- 框架：FastAPI + Uvicorn
- 数据库：MySQL `eucal_ai_user`
- 缓存：Redis db/0（JWT 黑名单）、db/2（模型目录缓存）
- 公网域名：`user-api.eucal.ai`

## 前置条件

- 基础设施已启动（见 [infra.md](infra.md)）
- MySQL 中 `eucal_ai_user` 数据库已创建（infra 启动时自动完成）

## 文件清单

| 文件 | 用途 |
|------|------|
| `Dockerfile.user-service` | 多阶段构建镜像 |
| `docker-compose.backend.yml` | 容器编排（与 admin-service、user-worker 共用） |
| `env/backend.env.example` | 环境变量模板 |

## 镜像构建

```bash
# 单独构建
docker build -f deploy/Dockerfile.user-service -t eucal-user-service .

# 或通过 compose 构建
docker compose -f deploy/docker-compose.backend.yml build user-service
```

镜像内容：
- `src/common/` — 共享库
- `src/user_service/` — 服务代码
- `migrations/user_service/` — Alembic 迁移文件
- `scripts/` — 运维脚本（migrate.py、runtime_probe.py 等）

## 环境变量

### 数据库

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `USER_DATABASE_URL` | 是 | — | MySQL 连接串，格式：`mysql+aiomysql://user:pass@host:3306/eucal_ai_user` |
| `DATABASE_POOL_SIZE` | 否 | `10` | 连接池大小 |
| `DATABASE_MAX_OVERFLOW` | 否 | `20` | 连接池最大溢出 |
| `DATABASE_ECHO` | 否 | `false` | 是否打印 SQL 日志 |

### 认证

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `JWT_SECRET_KEY` | 是 | — | JWT 签名密钥，最少 32 字符 |
| `JWT_ALGORITHM` | 否 | `HS256` | JWT 算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `15` | Access Token 过期时间（分钟） |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 否 | `7` | Refresh Token 过期时间（天） |

### 服务间通信

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `INTERNAL_SECRET` | 是 | — | HMAC 签名密钥，最少 32 字符，所有服务必须一致 |
| `ADMIN_SERVICE_URL` | 是 | `http://localhost:8001` | admin-service 地址（Docker 内用 `http://admin-service:8001`） |

### Redis

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `REDIS_URL` | 否 | `redis://127.0.0.1:6379/0` | JWT 黑名单 Redis（Docker 内用 `redis://redis:6379/0`） |
| `CACHE_REDIS_URL` | 否 | `redis://127.0.0.1:6379/2` | 模型目录缓存 Redis（Docker 内用 `redis://redis:6379/2`） |

### Cookie / CORS

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ALLOWED_HOSTS` | 否 | — | CORS 允许的源，逗号分隔 |
| `COOKIE_SECURE` | 否 | `true` | Cookie Secure 标志（生产环境必须 true） |
| `COOKIE_SAMESITE` | 否 | `none` | Cookie SameSite 策略 |

### 邮件

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SMTP_HOST` | 否 | — | SMTP 服务器地址 |
| `SMTP_PORT` | 否 | `587` | SMTP 端口 |
| `SMTP_USER` | 否 | — | SMTP 用户名 |
| `SMTP_PASSWORD` | 否 | — | SMTP 密码 |
| `SMTP_TLS` | 否 | `true` | 是否启用 TLS |
| `SMTP_FROM` | 否 | `Eucal AI` | 发件人名称 |

### 其他

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SNOWFLAKE_WORKER_ID` | 否 | `1` | Snowflake ID 工作节点 |
| `SNOWFLAKE_DATACENTER_ID` | 否 | `1` | Snowflake ID 数据中心 |
| `DEBUG` | 否 | `false` | 调试模式 |

## 部署步骤

### 1. 准备环境文件

```bash
cp deploy/env/backend.env.example deploy/env/backend.env
# 编辑 backend.env，填入真实的密钥和配置
```

### 2. 运行数据库迁移

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm user-service \
  python scripts/migrate.py --service user-service upgrade head
```

### 3. 启动服务

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml up -d user-service
```

### 4. 验证

```bash
# 检查容器状态
docker compose -f deploy/docker-compose.backend.yml ps user-service

# 健康检查
curl -s http://localhost:8000/health | python -m json.tool

# 就绪检查（含数据库 + Redis 连通性）
curl -s http://localhost:8000/ready | python -m json.tool
```

## 健康检查

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /health` | — | 始终返回 200，确认进程存活 |
| `GET /ready` | — | 检查 MySQL + Redis 连通性，返回 200 或 503 |

Docker 内部健康检查使用 `scripts/runtime_probe.py http-ready --port 8000`，间隔 30s。

## 服务依赖

```
user-service
├── MySQL (eucal_ai_user)     — 必须
├── Redis db/0                — 必须（JWT 黑名单）
├── Redis db/2                — 必须（模型目录缓存）
└── admin-service             — 运行时依赖（模型目录网关代理）
```

user-service 启动时会调用 `ensure_database_at_head()` 检查 Alembic 迁移版本。如果数据库 schema 不在最新版本，服务会拒绝启动并报错。

## 数据库表

user-service 拥有 `eucal_ai_user` 数据库，包含以下表：

| 表 | 用途 |
|----|------|
| `users` | 用户账户 |
| `email_verification_codes` | 邮箱验证码 |
| `user_sessions` | 用户会话 |
| `user_api_keys` | API 密钥 |
| `balance_transactions` | 余额流水（不可变追加） |
| `topup_orders` | 充值订单 |
| `api_call_logs` | API 调用日志 |
| `usage_stats` | 小时级使用统计 |
| `voucher_redemption_codes` | 代金券兑换码 |

## 运维操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.backend.yml logs -f user-service
```

### 重启

```bash
docker compose -f deploy/docker-compose.backend.yml restart user-service
```

### 扩缩容

Uvicorn workers 数量通过 compose 中的 command 参数控制（默认 2）。
如需调整，修改 `docker-compose.backend.yml` 中 user-service 的 command：

```yaml
command: ["...uvicorn", "user_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 数据库迁移回滚

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm user-service \
  python scripts/migrate.py --service user-service downgrade -1
```
