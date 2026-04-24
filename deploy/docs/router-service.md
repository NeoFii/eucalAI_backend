# router-service 部署

## 概述

router-service 是面向公网的 API 网关，提供 OpenAI 兼容的 LLM 推理接口。它接收用户请求，验证 API Key，通过 inference-service 进行难度分类，然后路由到上游 LLM 提供商。

- 端口：8003
- 框架：FastAPI + Uvicorn
- 数据库：无
- 缓存：无
- 公网域名：`api.eucal.ai`
- 部署位置：独立机器（CPU-only）

## 前置条件

- backend 节点已部署且可达（user-service:8000、admin-service:8001）
- inference 节点已部署且可达（inference-service:8004）
- 上游 LLM API Key 已准备（autodl / aiping / openrouter）

## 文件清单

| 文件 | 用途 |
|------|------|
| `Dockerfile.router-cpu` | CPU-only 多阶段构建镜像 |
| `docker-compose.router.yml` | 容器编排 |
| `router/runtime_config.json` | 路由策略 fallback 配置（镜像内置） |
| `env/router.env.example` | 环境变量模板 |

## 镜像构建

```bash
docker build -f deploy/Dockerfile.router-cpu -t eucal-router-service .

# 或通过 compose
docker compose -f deploy/docker-compose.router.yml build router-service
```

镜像内容：
- `src/common/` — 共享库
- `src/router_service/` — 服务代码
- `deploy/router/` — 路由策略配置
- `scripts/` — 运维脚本

注意：router 镜像不包含 torch/transformers 等 ML 依赖，体积远小于 inference 镜像。

## 环境变量

### 服务发现

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `USER_SERVICE_URL` | 是 | `http://10.0.0.10:8000` | user-service 地址（VPC 内网 IP） |
| `ADMIN_SERVICE_URL` | 是 | `http://10.0.0.10:8001` | admin-service 地址（VPC 内网 IP） |
| `INFERENCE_SERVICE_URL` | 是 | `http://10.0.0.20:8004` | inference-service 地址（VPC 内网 IP） |

### 安全

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `INTERNAL_SECRET` | 是 | — | HMAC 签名密钥，与 backend 节点一致 |
| `INFERENCE_SERVICE_SECRET` | 是 | — | inference-service 共享密钥，与 GPU 节点一致 |

### 熔断器 / 重试

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `INTERNAL_HTTP_MAX_RETRIES` | 否 | `1` | 内部 HTTP 调用最大重试次数 |
| `INTERNAL_HTTP_RETRY_BACKOFF_SECONDS` | 否 | `0.2` | 重试退避时间（秒） |
| `INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD` | 否 | `3` | 熔断器触发阈值（连续失败次数） |
| `INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | 否 | `30` | 熔断器冷却时间（秒） |

### 配置刷新

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `CONFIG_REFRESH_INTERVAL_SECONDS` | 否 | `60` | 从 admin-service 拉取路由配置的间隔 |
| `CONFIG_FETCH_TIMEOUT_SECONDS` | 否 | `5` | 配置拉取超时 |

### 上游 LLM API Key

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AUTODL_API_KEY` | 条件 | — | AutoDL 平台 API Key |
| `AIPING_API_KEY` | 条件 | — | AiPing 平台 API Key |
| `OPENROUTER_API_KEY` | 条件 | — | OpenRouter 平台 API Key |

至少需要配置一个上游 API Key，否则无法路由请求。

### 其他

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DEBUG` | 否 | `false` | 调试模式 |

## 部署步骤

### 1. 准备环境文件

```bash
cp deploy/env/router.env.example deploy/env/router.env
# 编辑 router.env：
# - 填入 backend 节点和 GPU 节点的 VPC 内网 IP
# - 填入 INTERNAL_SECRET（与 backend 节点一致）
# - 填入 INFERENCE_SERVICE_SECRET（与 GPU 节点一致）
# - 填入至少一个上游 LLM API Key
```

### 2. 启动服务

```bash
docker compose --env-file deploy/env/router.env \
  -f deploy/docker-compose.router.yml up -d
```

### 3. 验证

```bash
# 健康检查
curl -s http://localhost:8003/ready

# 测试 OpenAI 兼容接口（需要有效的 API Key）
curl -s http://localhost:8003/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 请求路由流程

```
用户请求 → router-service (:8003)
  │
  ├─ 1. HMAC → user-service: 验证 API Key
  │
  ├─ 2. 判断请求模型
  │     ├─ model == "auto" → Secret → inference-service: 难度分类
  │     │                     返回 tier (1-5) → 映射到具体模型
  │     └─ model == 具体名称 → 跳过分类，直接路由
  │
  ├─ 3. 查找模型对应的上游 provider
  │
  ├─ 4. litellm → 上游 LLM API
  │
  └─ 5. HMAC → user-service: 写入调用日志 + 扣费
```

路由配置来源（三级降级）：
1. admin-service（HMAC 拉取，60s 轮询）
2. 上次成功的缓存配置
3. 本地 `deploy/router/runtime_config.json`（镜像内置 fallback）

## 健康检查

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /ready` | — | 返回 `{"status": "ok"}` |

Docker 内部健康检查：`scripts/runtime_probe.py http-ready --port 8003`，间隔 30s，启动等待 20s。

## 服务依赖

```
router-service
├── user-service              — 运行时必须（API Key 验证、调用日志）
├── admin-service             — 运行时必须（路由配置拉取）
├── inference-service         — 运行时可选（仅 model=auto 时需要）
└── 上游 LLM API              — 运行时必须（autodl / aiping / openrouter）
```

router-service 是无状态服务，不依赖数据库或 Redis。

## 网络安全

router-service 是唯一面向公网的后端服务：

- 公网仅暴露 8003 端口，通过 HTTPS 反向代理（云负载均衡器或 Nginx）
- 到 backend 节点的流量走 VPC 内网
- 到 GPU 节点的流量走 VPC 内网

安全组规则：
```
入站：公网 → :8003（仅 HTTPS）
出站：→ backend:8000, backend:8001（VPC 内网）
出站：→ GPU:8004（VPC 内网）
出站：→ 上游 LLM API（公网 HTTPS）
```

## 运维操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.router.yml logs -f router-service
```

### 重启

```bash
docker compose -f deploy/docker-compose.router.yml restart router-service
```

### 扩缩容

默认 4 个 Uvicorn workers。调整方式：修改 `docker-compose.router.yml` 中的 command 参数。

router-service 是无状态的，也可以通过部署多个实例 + 负载均衡来水平扩展。

### TLS 终止

router-service 本身不处理 TLS。推荐在前面放置：
- 云负载均衡器（ALB / CLB）
- 或 Nginx 反向代理

```nginx
server {
    listen 443 ssl;
    server_name api.eucal.ai;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
