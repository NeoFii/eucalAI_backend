# user-service

用户侧服务：用户认证、计费与余额、API Key 管理、调用日志、用量统计、兑换码、邮箱验证。

- 端口：8000
- 数据库：MySQL `eucal_ai_user`
- Redis：db/0（通用）、db/1（arq 任务队列）、db/2（缓存）

## 本地开发

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入数据库地址、JWT 密钥、SMTP 配置等

# 3. 环境检查
uv run check-env

# 4. 数据库迁移
uv run alembic -c migrations/alembic.ini upgrade head

# 5. 启动服务
uv run uvicorn user_service.main:app --host 0.0.0.0 --port 8000 --reload

# 6. 启动 Worker（可选，新开终端）
uv run arq user_service.worker.WorkerSettings
```

## Worker 定时任务

- `aggregate_usage_stats` — 每小时聚合用量统计
- `cleanup_expired_verification_codes` — 每天凌晨 3 点清理过期验证码

## 健康检查

- `GET /health` — 存活探针
- `GET /ready` — 就绪探针（检查数据库连接和 schema 版本）
