# inference-service 部署

## 概述

inference-service 是 GPU 推理服务，运行 Qwen2.5-7B backbone + 5 个 CG-TabM 分类头，为 router-service 提供输入难度分类能力。

- 端口：8004
- 框架：FastAPI + Uvicorn
- 数据库：无
- GPU：需要 1 块 NVIDIA GPU
- 部署位置：GPU 节点（10.0.0.20）

## 前置条件

- NVIDIA GPU + NVIDIA Container Toolkit（nvidia-docker）已安装
- 模型权重文件已放置在宿主机指定目录
- backend 节点已部署且 admin-service 可达（用于拉取路由配置）

## 文件清单

| 文件 | 用途 |
|------|------|
| `Dockerfile.inference` | GPU 镜像，安装 torch/transformers |
| `docker-compose.inference.yml` | 容器编排（GPU 资源预留） |
| `router/runtime_config.json` | 路由策略 fallback 配置（镜像内置） |
| `router/model_paths.json` | 模型资产路径映射（镜像内置） |
| `env/inference.env.example` | 环境变量模板 |

## 镜像构建

```bash
docker build -f deploy/Dockerfile.inference -t eucal-inference-service .

# 或通过 compose
docker compose -f deploy/docker-compose.inference.yml build inference-service
```

镜像特点：
- 使用 `uv sync --extra inference` 安装 ML 依赖（torch、transformers、numpy、pandas、scikit-learn）
- 镜像体积较大（约 3-5GB），构建时间较长
- 包含 `src/common/` + `src/inference_service/` + `deploy/router/` + `scripts/`

## 环境变量

### 服务间通信

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ADMIN_SERVICE_URL` | 是 | `http://10.0.0.10:8001` | admin-service 地址（VPC 内网 IP） |
| `INTERNAL_SECRET` | 是 | — | HMAC 签名密钥，与 backend 节点一致 |
| `INFERENCE_SERVICE_SECRET` | 是 | — | 共享密钥，router-service 用此密钥调用本服务 |

### 模型配置

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ROUTER_MODEL_PATHS` | 否 | `/app/deploy/router/model_paths.json` | 模型资产路径映射文件 |
| `ROUTER_RUNTIME_CONFIG` | 否 | `/app/deploy/router/runtime_config.json` | 路由策略配置文件 |
| `MODEL_WEIGHTS_HOST_PATH` | 是 | `/srv/eucal/models` | 宿主机上模型权重目录 |

### GPU

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `CUDA_VISIBLE_DEVICES` | 否 | `0` | 使用的 GPU 设备编号 |

### 配置刷新

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `CONFIG_REFRESH_INTERVAL_SECONDS` | 否 | `60` | 从 admin-service 拉取路由配置的间隔 |
| `CONFIG_FETCH_TIMEOUT_SECONDS` | 否 | `5` | 配置拉取超时 |

### 其他

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DEBUG` | 否 | `false` | 调试模式 |

## 模型权重准备

### 目录结构

模型权重需要放在宿主机的 `MODEL_WEIGHTS_HOST_PATH`（默认 `/srv/eucal/models`）目录下。
容器会将该目录只读挂载到 `/app/models`。

`deploy/router/model_paths.json` 定义了容器内的模型路径映射，确保目录结构与配置一致。

### 验证模型文件

```bash
# 检查宿主机模型目录
ls -la /srv/eucal/models/

# 查看 model_paths.json 中期望的路径
cat deploy/router/model_paths.json
```

## 部署步骤

### 1. 验证 GPU 环境

```bash
# 确认 NVIDIA 驱动
nvidia-smi

# 确认 NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 2. 准备模型权重

将模型权重文件放置到 `/srv/eucal/models/`（或自定义路径）。

### 3. 准备环境文件

```bash
cp deploy/env/inference.env.example deploy/env/inference.env
# 编辑 inference.env：
# - 填入 backend 节点的 VPC 内网 IP
# - 填入 INTERNAL_SECRET（与 backend 节点一致）
# - 填入 INFERENCE_SERVICE_SECRET（与 router 节点一致）
# - 如果模型路径不是默认的 /srv/eucal/models，修改 MODEL_WEIGHTS_HOST_PATH
```

### 4. 启动服务

```bash
docker compose --env-file deploy/env/inference.env \
  -f deploy/docker-compose.inference.yml up -d
```

### 5. 验证

```bash
# 检查容器状态（注意 start_period 为 120s，模型加载需要时间）
docker compose -f deploy/docker-compose.inference.yml ps inference-service

# 查看日志确认模型加载完成
docker compose -f deploy/docker-compose.inference.yml logs -f inference-service

# 健康检查
curl -s http://localhost:8004/ready
```

## 健康检查

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /ready` | — | 返回 `{"status": "ok"}`（模型加载完成后） |

Docker 内部健康检查：`scripts/runtime_probe.py http-ready --port 8004`
- 间隔：30s
- 超时：15s
- 重试：3 次
- 启动等待：120s（模型加载时间）

## 服务依赖

```
inference-service
├── NVIDIA GPU               — 必须（1 块）
├── 模型权重文件              — 必须（宿主机挂载）
└── admin-service             — 运行时依赖（路由配置刷新，60s 轮询）
```

inference-service 是无状态服务（不依赖数据库或 Redis），但需要 GPU 和模型权重。

## 认证机制

inference-service 使用简单的共享密钥认证（不是 HMAC 签名）：
- router-service 在请求头中携带 `X-Inference-Secret`
- inference-service 通过 `hmac.compare_digest` 比对
- 密钥由 `INFERENCE_SERVICE_SECRET` 环境变量配置

## GPU 资源

`docker-compose.inference.yml` 中配置了 GPU 资源预留：

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

默认使用 1 块 GPU。Uvicorn 固定 1 个 worker（GPU 推理不适合多 worker）。

## 运维操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.inference.yml logs -f inference-service
```

### 重启

```bash
docker compose -f deploy/docker-compose.inference.yml restart inference-service
```

注意：重启后需要等待模型重新加载（约 60-120s）。

### 监控 GPU 使用

```bash
# 宿主机上
nvidia-smi -l 5

# 或进入容器
docker compose -f deploy/docker-compose.inference.yml exec inference-service nvidia-smi
```

### 更新模型权重

1. 停止服务
2. 替换宿主机上的模型文件
3. 重新启动服务

```bash
docker compose -f deploy/docker-compose.inference.yml down
# 更新 /srv/eucal/models/ 中的文件
docker compose --env-file deploy/env/inference.env \
  -f deploy/docker-compose.inference.yml up -d
```
