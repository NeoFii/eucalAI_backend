# router-service

公共 API 网关：OpenAI 兼容接口、智能路由、难度分类调度、上游 LLM 转发、速率限制、渠道亲和。

- 端口：8003
- 无数据库
- Redis（可选）：速率限制、渠道亲和、调用日志缓冲

## 本地开发

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入服务地址、密钥、上游 API Key 等

# 3. 环境检查
uv run check-env

# 4. 启动服务
uv run uvicorn router_service.main:app --host 0.0.0.0 --port 8003 --reload
```

## 依赖服务

router-service 启动前需要以下服务可用：

- **user-service**（`USER_SERVICE_URL`）— API Key 验证、调用日志写入
- **admin-service**（`ADMIN_SERVICE_URL`）— 路由配置拉取
- **inference-service**（`INFERENCE_SERVICE_URL`）— prompt 难度分类

如果依赖服务不可用，router 会使用 `config/runtime_config.json` 作为回退配置。

## 健康检查

- `GET /health` — 存活探针
- `GET /ready` — 就绪探针
