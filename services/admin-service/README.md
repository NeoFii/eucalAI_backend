# admin-service

管理控制面服务：管理员认证、模型目录、路由配置、审计日志、供应商凭证管理、资源池管理。

- 端口：8001
- 数据库：MySQL `eucal_ai_admin`
- Redis：db/0（通用）、db/3（arq 任务队列）

## 本地开发

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入数据库地址、JWT 密钥等

# 3. 环境检查
uv run check-env

# 4. 数据库迁移
uv run alembic -c migrations/alembic.ini upgrade head

# 5. 启动服务
uv run uvicorn admin_service.main:app --host 0.0.0.0 --port 8001 --reload

# 6. 启动 Worker（可选，新开终端）
uv run arq admin_service.worker.WorkerSettings
```

## 首次部署

首次启动需要初始化超级管理员，在 `.env` 中设置：

```dotenv
BOOTSTRAP_SUPERADMIN_ENABLED=true
BOOTSTRAP_SUPERADMIN_EMAIL=founder@example.com
BOOTSTRAP_SUPERADMIN_PASSWORD=StrongPassword123!
BOOTSTRAP_SUPERADMIN_NAME=System Founder
```

启动后设置 `BOOTSTRAP_SUPERADMIN_ENABLED=false`。

## 路由配置种子数据

```bash
uv run seed-routing-config              # 从 config/runtime_config.json 导入
uv run seed-routing-config --dry-run    # 预览不写入
```

## 健康检查

- `GET /health` — 存活探针
- `GET /ready` — 就绪探针（检查数据库连接和 schema 版本）
