# admin-service 部署

## 概述

admin-service 是管理后台的核心服务，负责管理员认证、模型目录管理、路由配置管理、Provider 凭证管理和审计日志。

- 端口：8001
- 框架：FastAPI + Uvicorn
- 数据库：MySQL `eucal_ai_admin`
- 缓存：Redis db/0（JWT 黑名单）
- 公网域名：`admin-api.eucal.ai`

## 前置条件

- 基础设施已启动（见 [infra.md](infra.md)）
- MySQL 中 `eucal_ai_admin` 数据库已创建（infra 启动时自动完成）

## 文件清单

| 文件 | 用途 |
|------|------|
| `Dockerfile.admin-service` | 多阶段构建镜像 |
| `docker-compose.backend.yml` | 容器编排 |
| `router/runtime_config.json` | 路由策略 fallback 配置（镜像内置） |
| `env/backend.env.example` | 环境变量模板 |

## 镜像构建

```bash
docker build -f deploy/Dockerfile.admin-service -t eucal-admin-service .

# 或通过 compose
docker compose -f deploy/docker-compose.backend.yml build admin-service
```

镜像内容：
- `src/common/` — 共享库
- `src/admin_service/` — 服务代码
- `migrations/admin_service/` — Alembic 迁移文件
- `deploy/router/` — 路由策略配置（seed 脚本需要）
- `scripts/` — 运维脚本

## 环境变量

### 数据库

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ADMIN_DATABASE_URL` | 是 | — | MySQL 连接串，格式：`mysql+aiomysql://user:pass@host:3306/eucal_ai_admin` |
| `DATABASE_POOL_SIZE` | 否 | `10` | 连接池大小 |
| `DATABASE_MAX_OVERFLOW` | 否 | `20` | 连接池最大溢出 |
| `DATABASE_ECHO` | 否 | `false` | 是否打印 SQL 日志 |

### 认证

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `JWT_SECRET_KEY` | 是 | — | JWT 签名密钥，最少 32 字符 |
| `JWT_ALGORITHM` | 否 | `HS256` | JWT 算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `60` | 管理员 Access Token 过期时间（分钟） |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 否 | `7` | Refresh Token 过期时间（天） |

### 安全

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `INTERNAL_SECRET` | 是 | — | HMAC 签名密钥，最少 32 字符 |
| `PROVIDER_SECRET_MASTER_KEY` | 是 | — | AES-256-GCM 主密钥，64 字符十六进制，用于加密 Provider API Key |

### 服务间通信

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `USER_SERVICE_URL` | 是 | `http://localhost:8000` | user-service 地址（Docker 内用 `http://user-service:8000`） |
| `REDIS_URL` | 否 | `redis://127.0.0.1:6379/0` | JWT 黑名单 Redis |

### Cookie / CORS

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ALLOWED_HOSTS` | 否 | — | CORS 允许的源，逗号分隔 |
| `COOKIE_SECURE` | 否 | `true` | Cookie Secure 标志 |
| `COOKIE_SAMESITE` | 否 | `none` | Cookie SameSite 策略 |

### 超级管理员引导

首次部署时需要创建超级管理员账户：

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `BOOTSTRAP_SUPERADMIN_ENABLED` | 否 | `false` | 是否启用自动创建超级管理员 |
| `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP` | 否 | `true` | 启动时是否要求引导完成 |
| `BOOTSTRAP_SUPERADMIN_EMAIL` | 条件 | — | 超级管理员邮箱（启用引导时必填） |
| `BOOTSTRAP_SUPERADMIN_PASSWORD` | 条件 | — | 超级管理员密码（启用引导时必填） |
| `BOOTSTRAP_SUPERADMIN_NAME` | 条件 | — | 超级管理员显示名（启用引导时必填） |
| `BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS` | 否 | `false` | 已存在时是否重置密码 |
| `BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS` | 否 | `false` | 已存在时是否更新名称 |

### 其他

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SNOWFLAKE_WORKER_ID` | 否 | `2` | Snowflake ID 工作节点（不能与 user-service 相同） |
| `SNOWFLAKE_DATACENTER_ID` | 否 | `1` | Snowflake ID 数据中心 |
| `DEBUG` | 否 | `false` | 调试模式 |

## 部署步骤

### 1. 准备环境文件

```bash
cp deploy/env/backend.env.example deploy/env/backend.env
# 编辑 backend.env，特别注意：
# - PROVIDER_SECRET_MASTER_KEY 必须是 64 字符十六进制字符串
# - 首次部署设置 BOOTSTRAP_SUPERADMIN_ENABLED=true 并填写管理员信息
```

生成 `PROVIDER_SECRET_MASTER_KEY`：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. 运行数据库迁移

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm admin-service \
  python scripts/migrate.py --service admin-service upgrade head
```

迁移会自动创建所有表并插入种子数据（模型供应商、分类、默认模型）。

### 3. 启动服务

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml up -d admin-service
```

首次启动时，如果 `BOOTSTRAP_SUPERADMIN_ENABLED=true`，会自动创建超级管理员账户。

### 4. 验证

```bash
# 健康检查
curl -s http://localhost:8001/health | python -m json.tool

# 就绪检查
curl -s http://localhost:8001/ready | python -m json.tool
```

### 5. 种子路由配置（可选）

如果需要初始化路由配置：

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm admin-service \
  python -m scripts.seed_routing_config
```

## 健康检查

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /health` | — | 始终返回 200 |
| `GET /ready` | — | 检查 MySQL + Redis 连通性 |

Docker 内部健康检查：`scripts/runtime_probe.py http-ready --port 8001`，间隔 30s，启动等待 40s。

## 服务依赖

```
admin-service
├── MySQL (eucal_ai_admin)    — 必须
├── Redis db/0                — 必须（JWT 黑名单）
└── user-service              — 运行时依赖（用户管理、代金券、使用统计的网关调用）
```

admin-service 启动时会：
1. 调用 `ensure_database_at_head()` 检查迁移版本
2. 执行超级管理员引导（如果启用）

## 数据库表

admin-service 拥有 `eucal_ai_admin` 数据库，包含以下表：

| 表 | 用途 |
|----|------|
| `admin_users` | 管理员账户（uid 为 NanoID） |
| `admin_audit_logs` | 审计日志（不可变追加） |
| `model_vendors` | 模型供应商目录 |
| `model_categories` | 模型分类目录 |
| `supported_models` | 支持的模型列表 |
| `supported_model_category_map` | 模型-分类多对多映射 |
| `routing_configs` | 路由策略版本管理 |
| `provider_credentials` | Provider API Key（AES-256-GCM 加密存储） |

## 安全注意事项

- `PROVIDER_SECRET_MASTER_KEY` 是加密 Provider API Key 的主密钥，丢失将导致所有已存储的凭证无法解密。务必安全备份。
- `BOOTSTRAP_SUPERADMIN_ENABLED` 在首次部署完成后应设为 `false`，避免每次重启都尝试引导。

## 运维操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.backend.yml logs -f admin-service
```

### 重启

```bash
docker compose -f deploy/docker-compose.backend.yml restart admin-service
```

### 数据库迁移回滚

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm admin-service \
  python scripts/migrate.py --service admin-service downgrade -1
```
