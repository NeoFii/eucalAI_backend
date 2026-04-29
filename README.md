# Eucal AI Backend

AI 智能路由平台后端。通过 ML 模型对用户 prompt 进行难度分类，然后路由到合适的上游 LLM 供应商。

## 架构

| 服务 | 端口 | 存储 | 说明 |
| --- | ---: | --- | --- |
| admin-service | 8001 | MySQL `eucal_ai_admin` | 管理员认证、模型目录、路由配置、审计日志 |
| user-service | 8000 | MySQL `eucal_ai_user` | 用户认证、计费、API Key、用量统计 |
| router-service | 8003 | 无（可选 Redis） | 公共 API 网关、智能路由、上游 LLM 转发 |
| inference-service | 8004 | 无（需要 GPU） | ML 推理，prompt 难度分类 |

每个服务完全自包含在 `services/<name>/` 下，拥有独立的 Dockerfile、docker-compose.yml、.env.example 和配置文件。

## 项目结构

```
services/
├── admin-service/           # 管理控制面
├── user-service/            # 用户侧 API
├── router-service/          # 公共 API 网关
└── inference-service/       # GPU ML 推理
infra/
├── docker-compose.yml       # 生产环境 MySQL + Redis
└── docker-compose.local.yml # 本地开发 MySQL + Redis
```

## 本地开发

确保 MySQL 和 Redis 已在本地运行，按以下顺序启动各服务（每个服务开一个终端）：

```bash
# 1. admin-service（其他服务依赖它获取路由配置）
cd services/admin-service
cp .env.example .env  # 编辑填入实际值
uv sync
uv run check-env
uv run alembic -c migrations/alembic.ini upgrade head
uv run uvicorn admin_service.main:app --host 0.0.0.0 --port 8001 --reload

# 2. user-service（router 依赖它做 API Key 验证）
cd services/user-service
cp .env.example .env
uv sync
uv run check-env
uv run alembic -c migrations/alembic.ini upgrade head
uv run uvicorn user_service.main:app --host 0.0.0.0 --port 8000 --reload

# 3. inference-service（需要 GPU，router 依赖它做 prompt 分类）
cd services/inference-service
cp .env.example .env
uv sync
uv run check-env
uv run uvicorn inference_service.main:app --host 0.0.0.0 --port 8004 --reload

# 4. router-service（最后启动，依赖上面三个）
cd services/router-service
cp .env.example .env
uv sync
uv run check-env
uv run uvicorn router_service.main:app --host 0.0.0.0 --port 8003 --reload
```

Worker 进程（可选，各开一个终端）：

```bash
cd services/admin-service && uv run arq admin_service.worker.WorkerSettings
cd services/user-service && uv run arq user_service.worker.WorkerSettings
```

各服务详细说明见 `services/<name>/README.md`。

## 部署

每个服务有独立的 `docker-compose.yml`，可单独部署：

```bash
# 基础设施（后端节点）
docker compose -f infra/docker-compose.yml up -d

# 后端服务
cd services/admin-service && docker compose up -d
cd services/user-service && docker compose up -d

# 路由网关（独立主机）
cd services/router-service && docker compose up -d

# GPU 推理（独立主机）
cd services/inference-service && docker compose up -d
```

## 服务间通信

- router → user-service：API Key 验证、调用日志批量写入（HMAC/INTERNAL_SECRET）
- router → admin-service：路由配置拉取（HMAC/INTERNAL_SECRET）
- router → inference-service：prompt 分类（X-Inference-Secret）
- admin → user-service：用户管理、兑换码（HMAC/INTERNAL_SECRET）
- inference → admin-service：配置刷新（HMAC/INTERNAL_SECRET）

## 共享密钥

| 变量 | 涉及服务 | 用途 |
| --- | --- | --- |
| `JWT_SECRET_KEY` | admin, user | JWT 签名（至少 32 字符） |
| `INTERNAL_SECRET` | admin, user, router, inference | HMAC 服务间签名 |
| `INFERENCE_SERVICE_SECRET` | router, inference | 路由到推理服务的认证 |
