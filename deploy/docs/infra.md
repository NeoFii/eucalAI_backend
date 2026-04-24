# 基础设施部署 — MySQL + Redis

## 概述

基础设施层提供 MySQL 8.0 和 Redis 7 两个有状态服务，供 backend 节点的所有应用服务使用。
基础设施通过 `docker-compose.infra.yml` 独立管理，与应用服务解耦，通过 Docker 网络 `eucal_backend_network` 通信。

## 前置条件

- Docker Engine 24+ 和 Docker Compose V2
- 宿主机至少 2GB 可用内存（MySQL 默认配置）
- 磁盘空间：MySQL 数据卷建议预留 10GB+

## 文件清单

| 文件 | 用途 |
|------|------|
| `docker-compose.infra.yml` | MySQL + Redis 容器编排 |
| `init-db.sql` | MySQL 首次启动时自动建库 |
| `env/backend.env.example` | 环境变量模板（`MYSQL_ROOT_PASSWORD` 等） |

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `MYSQL_ROOT_PASSWORD` | 是 | `change-me` | MySQL root 密码，生产环境必须修改 |

## 部署步骤

### 1. 准备环境文件

```bash
cp deploy/env/backend.env.example deploy/env/backend.env
```

编辑 `deploy/env/backend.env`，设置安全的 `MYSQL_ROOT_PASSWORD`。

### 2. 启动基础设施

```bash
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.infra.yml up -d
```

### 3. 验证服务健康

```bash
# MySQL
docker compose -f deploy/docker-compose.infra.yml ps mysql
# 状态应为 healthy

# Redis
docker compose -f deploy/docker-compose.infra.yml ps redis
# 状态应为 healthy

# 手动验证 MySQL 连接
docker compose -f deploy/docker-compose.infra.yml exec mysql \
  mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SHOW DATABASES;"
# 应看到 eucal_ai_admin 和 eucal_ai_user
```

## 数据库初始化

`init-db.sql` 在 MySQL 容器首次启动时自动执行，创建两个数据库：

```sql
CREATE DATABASE IF NOT EXISTS eucal_ai_admin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS eucal_ai_user  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

注意：`init-db.sql` 只在 MySQL 数据卷为空时执行（首次启动）。如果需要重新初始化，需先删除数据卷：

```bash
docker compose -f deploy/docker-compose.infra.yml down -v
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.infra.yml up -d
```

## 网络

infra compose 创建名为 `eucal_backend_network` 的 Docker 网络。
backend 应用服务的 compose 通过 `external: true` 加入同一网络，从而可以用容器名 `mysql`、`redis` 直接访问。

```
eucal_backend_network
├── mysql   (3306)
├── redis   (6379)
├── user-service    (通过 backend compose 加入)
├── admin-service   (通过 backend compose 加入)
└── user-worker     (通过 backend compose 加入)
```

## Redis 数据库分配

| DB | 用途 | 使用方 |
|----|------|--------|
| 0 | JWT 令牌黑名单 | user-service, admin-service |
| 1 | ARQ 任务队列 | user-worker |
| 2 | 模型目录缓存 | user-service |

## 持久化

| 服务 | Docker Volume | 说明 |
|------|--------------|------|
| MySQL | `eucal_mysql_data` | 所有业务数据，务必定期备份 |
| Redis | `eucal_redis_data` | 缓存和队列数据，丢失不影响业务（会自动重建） |

Redis 配置为纯内存模式（`--save "" --appendonly no`），重启后数据清空。这是预期行为——JWT 黑名单和缓存都是可重建的。

## 健康检查

| 服务 | 检查方式 | 间隔 | 超时 | 重试 | 启动等待 |
|------|---------|------|------|------|---------|
| MySQL | `mysqladmin ping` | 10s | 5s | 10 | 30s |
| Redis | `redis-cli ping` | 10s | 5s | 5 | — |

## 运维操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.infra.yml logs -f mysql
docker compose -f deploy/docker-compose.infra.yml logs -f redis
```

### 备份 MySQL

```bash
docker compose -f deploy/docker-compose.infra.yml exec mysql \
  mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --all-databases > backup_$(date +%Y%m%d).sql
```

### 重启单个服务

```bash
docker compose -f deploy/docker-compose.infra.yml restart mysql
docker compose -f deploy/docker-compose.infra.yml restart redis
```

## 启动顺序

基础设施必须在应用服务之前启动：

```
1. docker-compose.infra.yml    ← MySQL + Redis（本文档）
2. 运行数据库 migration         ← 见 user-service / admin-service 文档
3. docker-compose.backend.yml  ← 应用服务
```
