# 部署总览

Eucal AI 后端采用多机 Docker Compose 部署，按服务职责拆分为 3 个节点。

## 架构拓扑

```
┌─────────────────────────────────────────────────────────┐
│  Backend 节点 (10.0.0.10)                                │
│                                                          │
│  docker-compose.infra.yml     docker-compose.backend.yml │
│  ┌────────┐ ┌───────┐        ┌──────────────────┐       │
│  │ MySQL  │ │ Redis │        │ user-service     │       │
│  │ :3306  │ │ :6379 │        │ :8000            │       │
│  └────────┘ └───────┘        ├──────────────────┤       │
│                               │ admin-service    │       │
│                               │ :8001            │       │
│                               ├──────────────────┤       │
│                               │ user-worker      │       │
│                               │ (arq)            │       │
│                               └──────────────────┘       │
└──────────────────────────────────────────────────────────┘
                    ▲                    ▲
               HMAC │               HMAC │
                    │                    │
┌───────────────────┴────────────────────┴─────────────────┐
│  Router 节点 (独立机器, CPU)                               │
│                                                           │
│  docker-compose.router.yml                                │
│  ┌─────────────────────────────────────┐                  │
│  │ router-service :8003                │                  │
│  │ 公网 API 网关 (OpenAI 兼容)          │                  │
│  └─────────────────────────────────────┘                  │
└──────────────────────────┬────────────────────────────────┘
                    Secret │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  GPU 节点 (10.0.0.20)                                     │
│                                                           │
│  docker-compose.inference.yml                             │
│  ┌─────────────────────────────────────┐                  │
│  │ inference-service :8004             │                  │
│  │ Qwen2.5-7B + CG-TabM 分类          │                  │
│  └─────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────┘
```

## 服务清单

| 服务 | 端口 | 数据库 | 节点 | 文档 |
|------|------|--------|------|------|
| MySQL + Redis | 3306 / 6379 | — | Backend | [docs/infra.md](docs/infra.md) |
| user-service | 8000 | `eucal_ai_user` | Backend | [docs/user-service.md](docs/user-service.md) |
| admin-service | 8001 | `eucal_ai_admin` | Backend | [docs/admin-service.md](docs/admin-service.md) |
| user-worker | — | `eucal_ai_user` | Backend | [docs/user-worker.md](docs/user-worker.md) |
| router-service | 8003 | 无 | Router | [docs/router-service.md](docs/router-service.md) |
| inference-service | 8004 | 无 | GPU | [docs/inference-service.md](docs/inference-service.md) |

## 文件结构

```
deploy/
├── docs/                          # 各服务部署文档
│   ├── infra.md
│   ├── user-service.md
│   ├── admin-service.md
│   ├── user-worker.md
│   ├── router-service.md
│   └── inference-service.md
├── Dockerfile.user-service        # user-service 镜像
├── Dockerfile.admin-service       # admin-service 镜像
├── Dockerfile.user-worker         # user-worker 镜像
├── Dockerfile.router-cpu          # router-service 镜像 (CPU-only)
├── Dockerfile.inference           # inference-service 镜像 (GPU)
├── docker-compose.infra.yml       # 基础设施 (MySQL + Redis)
├── docker-compose.backend.yml     # 应用服务 (user + admin + worker)
├── docker-compose.router.yml      # 路由网关
├── docker-compose.inference.yml   # GPU 推理
├── docker-compose.local-infra.yml # 本地开发用基础设施
├── init-db.sql                    # MySQL 初始化建库
├── env/                           # 环境变量模板
│   ├── backend.env.example
│   ├── router.env.example
│   └── inference.env.example
└── router/                        # 路由策略配置
    ├── runtime_config.json
    └── model_paths.json
```

## 快速部署（全流程）

### 1. 准备环境文件

```bash
cp deploy/env/backend.env.example   deploy/env/backend.env
cp deploy/env/router.env.example    deploy/env/router.env
cp deploy/env/inference.env.example deploy/env/inference.env
```

编辑各 `.env` 文件，填入真实的密钥和网络地址。

### 2. Backend 节点

```bash
# 启动基础设施
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.infra.yml up -d

# 等待 MySQL 就绪
docker compose -f deploy/docker-compose.infra.yml ps

# 运行数据库迁移
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm admin-service \
  python scripts/migrate.py --service admin-service upgrade head

docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml \
  run --rm user-service \
  python scripts/migrate.py --service user-service upgrade head

# 启动应用服务
docker compose --env-file deploy/env/backend.env \
  -f deploy/docker-compose.backend.yml up -d
```

### 3. GPU 节点

```bash
# 确认 GPU 环境
nvidia-smi

# 放置模型权重到 /srv/eucal/models/

# 启动推理服务
docker compose --env-file deploy/env/inference.env \
  -f deploy/docker-compose.inference.yml up -d
```

### 4. Router 节点

```bash
docker compose --env-file deploy/env/router.env \
  -f deploy/docker-compose.router.yml up -d
```

### 5. 验证

```bash
# Backend 节点
curl -s http://localhost:8000/ready   # user-service
curl -s http://localhost:8001/ready   # admin-service

# Router 节点
curl -s http://localhost:8003/ready   # router-service

# GPU 节点
curl -s http://localhost:8004/ready   # inference-service
```

## 日志

所有服务默认向 stdout 输出结构化 JSON 日志，字段包含 `timestamp`、`service`、`event`、`level`、`request_id`。Compose 文件同时将 `/app/logs` 挂载为可选文件日志目录，并默认启用 `LOG_TO_FILE=true`，可通过环境变量统一调整：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | stdout 与文件日志级别 |
| `LOG_TO_FILE` | `true` | 是否写入 `/app/logs/<service>.log` |
| `LOG_FILE_MAX_BYTES` | `52428800` | 单个日志文件轮转大小 |
| `LOG_FILE_BACKUP_COUNT` | `5` | 保留轮转文件数 |

router-service 额外保留业务观测 JSONL：`/app/logs/routing.jsonl` 与 `/app/logs/upstream.jsonl`。这两个文件包含统一的 `ts`、`service`、`event`、`request_id`、`router_trace_id` 字段，并对 prompt/response 预览做截断和敏感信息脱敏。

## 公网域名

| 域名 | 目标 | 说明 |
|------|------|------|
| `api.eucal.ai` | router-service:8003 | OpenAI 兼容 API 入口 |
| `user-api.eucal.ai` | user-service:8000 | 用户端 API |
| `admin-api.eucal.ai` | admin-service:8001 | 管理端 API |

TLS 在云负载均衡器或反向代理层终止。

## 安全组

| 规则 | 说明 |
|------|------|
| 公网 → Router:8003 | 仅 HTTPS |
| Router → Backend:8000, 8001 | VPC 内网 |
| Router → GPU:8004 | VPC 内网 |
| GPU → Backend:8001 | VPC 内网 |
| MySQL:3306, Redis:6379 | 仅 Backend 节点内部 Docker 网络 |

## 共享密钥

所有节点必须使用相同的 `INTERNAL_SECRET` 进行 HMAC 签名通信。
Router 和 GPU 节点还需要共享 `INFERENCE_SERVICE_SECRET`。

```bash
# 生成安全密钥
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
