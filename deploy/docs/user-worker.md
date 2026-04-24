# user-worker 部署

## 概述

user-worker 是基于 ARQ 的后台任务消费进程，运行 user-service 的异步任务。它不是 HTTP 服务，没有端口暴露。

- 框架：ARQ（Redis-based async task queue）
- 任务队列：Redis db/1
- 数据库：MySQL `eucal_ai_user`（与 user-service 共享）

## 前置条件

- 基础设施已启动（见 [infra.md](infra.md)）
- user-service 和 admin-service 已启动且健康（worker 的 depends_on 要求）
- 数据库迁移已完成（见 [user-service.md](user-service.md)）

## 文件清单

| 文件 | 用途 |
|------|------|
| `Dockerfile.user-worker` | 多阶段构建镜像 |
| `docker-compose.backend.yml` | 容器编排 |
| `env/backend.env.example` | 环境变量模板 |

## 镜像构建

```bash
docker build -f deploy/Dockerfile.user-worker -t eucal-user-worker .

# 或通过 compose
docker compose -f deploy/docker-compose.backend.yml build user-worker
```

镜像内容与 user-service 相同（`src/common/` + `src/user_service/` + `migrations/user_service/` + `scripts/`），但没有 EXPOSE，CMD 为 `arq user_service.worker.WorkerSettings`。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `USER_DATABASE_URL` | 是 | — | MySQL 连接串（与 user-service 相同） |
| `USER_QUEUE_REDIS_URL` | 否 | `redis://127.0.0.1:6379/1` | ARQ 任务队列 Redis（Docker 内用 `redis://redis:6379/1`） |
| `INTERNAL_SECRET` | 是 | — | HMAC 签名密钥 |
| `ADMIN_SERVICE_URL` | 是 | — | admin-service 地址（Docker 内用 `http://admin-service:8001`） |
| `SNOWFLAKE_DATACENTER_ID` | 否 | `1` | Snowflake ID 数据中心 |
| `DEBUG` | 否 | `false` | 调试模式 |

## 部署步骤

### 1. 确认前置服务已就绪

```bash
# user-service 和 admin-service 必须是 healthy 状态
docker compose -f deploy/docker-compose.backend.yml ps
```

### 2. 启动 worker

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml up -d user-worker
```

### 3. 验证

```bash
# 检查容器状态
docker compose -f deploy/docker-compose.backend.yml ps user-worker

# 查看日志确认 worker 已连接队列
docker compose -f deploy/docker-compose.backend.yml logs user-worker
```

## 定时任务

worker 内置两个 cron 任务：

| 任务 | 调度 | 说明 |
|------|------|------|
| `aggregate_usage_stats` | 每小时整点 | 聚合上一小时的 API 调用统计 |
| `cleanup_expired_verification_codes` | 每天 03:00 | 清理过期的邮箱验证码（默认保留 7 天） |

## 健康检查

worker 不是 HTTP 服务，健康检查通过 `runtime_probe.py worker-ready` 实现，检查：
- MySQL 数据库连通性
- Redis 任务队列连通性

```bash
# 手动检查
docker compose -f deploy/docker-compose.backend.yml exec user-worker \
  python scripts/runtime_probe.py worker-ready \
  --database-url-env USER_DATABASE_URL \
  --redis-url-env USER_QUEUE_REDIS_URL
```

Docker 内部健康检查间隔 30s。

## 服务依赖

```
user-worker
├── MySQL (eucal_ai_user)     — 必须（读写业务数据）
├── Redis db/1                — 必须（ARQ 任务队列）
├── user-service              — 启动依赖（必须 healthy）
└── admin-service             — 启动依赖（必须 healthy）
```

## 运维操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.backend.yml logs -f user-worker
```

### 重启

```bash
docker compose -f deploy/docker-compose.backend.yml restart user-worker
```

### 调整并发

worker 并发数通过环境变量 `USER_WORKER_CONCURRENCY` 控制（默认 5），任务超时通过 `USER_JOB_TIMEOUT_SECONDS` 控制（默认 300s）。

### 手动触发任务

如需手动触发使用统计聚合：

```bash
docker compose -f deploy/docker-compose.backend.yml exec user-worker \
  python -c "
import asyncio
from user_service.jobs import aggregate_usage_stats
asyncio.run(aggregate_usage_stats({}))
"
```
