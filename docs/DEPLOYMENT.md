# Eucal AI Backend — 部署架构文档

> 更新：2026-04-21
> 范围：三容器部署拓扑（backend-app / router-service / inference-service）

---

## 1. 总体拓扑

三容器设计：**控制面合一、网关可扩、推理独立**。

```
┌──────────────────────────────────────────────────────────────────────┐
│                    客户端 / 前端 / LLM 调用方                          │
└────────────────────┬──────────────────────┬──────────────────────────┘
                     │                      │
       ┌─────────────▼──────────────┐  ┌────▼─────────────────────────┐
       │   Container 1: backend-app │  │  Container 2: router-service │
       │          :8001             │  │          :8003               │
       │   CPU-only                 │  │   CPU-only, 水平扩展          │
       │                            │  │                              │
       │   admin + user + testing   │  │   HTTP 网关 / 流式转发        │
       │   scheduler + worker       │  │   API Key 校验               │
       │   + Redis                  │  │   上游供应商路由              │
       └────────────────────────────┘  └──────────────┬───────────────┘
                                                      │ POST /internal/v1/classify
                                       ┌──────────────▼───────────────┐
                                       │  Container 3: inference-svc  │
                                       │          :8004               │
                                       │   GPU, 独立扩缩              │
                                       │                              │
                                       │   Qwen backbone              │
                                       │   5× CG-TabM 路由器          │
                                       │   Proto 语义加权              │
                                       └──────────────────────────────┘
```

### 设计原则

| 原则 | 说明 |
|------|------|
| **控制面合一** | admin/user/testing 及后台任务共享一个容器，减少运维复杂度 |
| **网关无状态** | router-service 仅做 HTTP 转发 + 评分调用，不持有模型权重，可任意水平扩容 |
| **推理资源独立** | GPU 绑定的 Qwen + CG-TabM 独立部署，按 GPU 卡数扩缩，不影响网关可用性 |
| **ML 依赖隔离** | torch/transformers/numpy 仅存在于 inference-svc 镜像，router 和 backend-app 零 ML 依赖 |

---

## 2. Container 1: backend-app（控制面）

**职责**：承载全部管理面逻辑，非热路径。

| 进程 | 模块 | 端口 | 说明 |
|------|------|------|------|
| backend-app | `backend_app.main:app` | 8001 | admin + user + testing 合并 FastAPI |
| testing-scheduler | `testing_service.main:app` | 8012 | APScheduler 定时触发基准探测 |
| testing-worker | `testing_service.worker.WorkerSettings` | — | arq 队列消费者 |
| redis | redis:7-alpine | 6379 | 队列后端（scheduler + worker） |

**数据库**：3 个独立 MySQL 库（`eucal_ai_{admin,user,testing}`）

**扩缩特点**：
- 通常单实例足够（无状态，可多副本）
- scheduler 必须单实例（避免重复调度）
- worker 可按队列深度扩容

---

## 3. Container 2: router-service（CPU 网关）

**职责**：接收 LLM 请求，调用 inference-svc 获取路由决策，转发到上游供应商。

### 模块归属

| 模块 | 文件 | 说明 |
|------|------|------|
| FastAPI 路由 | `routers/chat.py`, `routers/completions.py` | `/v1/chat/completions`, `/v1/completions` |
| 上游转发 | `services/upstream.py` | 供应商目标解析 + litellm 调用 |
| API Key 网关 | `gateway.py` | user-service API Key 校验 |
| 配置 | `config.py` | runtime_config / model_paths 加载 |
| 入口 | `main.py`, `dependencies.py` | FastAPI app + 依赖注入 |

### 请求流程（拆分后）

```
客户端
  │
  ▼
router-service (CPU)
  │ 1. 解析请求，提取 messages
  │ 2. 若指定直接模型 → 跳过分类，直接转发
  │ 3. 若为路由别名 → POST inference-svc /internal/v1/classify
  │ 4. 收到 {selected_model, scores, tier} 响应
  │ 5. 根据 selected_model 转发到上游 LLM
  ▼
upstream LLM provider
```

**依赖**：无 torch/transformers/numpy，仅 FastAPI + httpx + litellm

**扩缩特点**：
- 纯 I/O 密集，CPU-only
- 可任意水平扩容（无状态、无模型权重）
- 主要瓶颈在上游 LLM 延迟，非本地计算

---

## 4. Container 3: inference-service（GPU 推理）

**职责**：加载 Qwen backbone + 5 CG-TabM 路由器，对请求进行难度分类和评分。

### 模块归属

| 模块 | 文件 | 说明 |
|------|------|------|
| 路由引擎 | `services/router_engine.py` | `HybridIntegratedDifficultyRouter` |
| CG-TabM 模型 | `nn/cg_tabm.py` | `CGTabMRegressor`（PyTorch nn.Module） |
| 探针模型 | `nn/probe.py` | 回归探针（PyTorch） |
| 输入构造 | `utils/input_builder.py` | 消息预处理、proto 语义文本构造 |
| 评分工具 | `utils/scoring.py` | 归一化、加权、层级映射 |

### 重 ML 依赖

- `torch`（CUDA / bfloat16 推理）
- `transformers`（AutoTokenizer, AutoModelForCausalLM — Qwen backbone）
- `numpy`（特征数组、proto 计算）
- `scikit-learn`（scaler — pickle 加载）

### 扩缩特点

- **GPU 绑定**：每实例至少 1 张 GPU 卡
- 模型启动加载一次（Qwen backbone ~数 GB），推理为 `@torch.no_grad()` 前向传播
- 按 GPU 卡数 / 推理 QPS 需求独立扩缩
- 与 router-service 容器数量解耦

---

## 5. 服务拆分边界 — classify 接口

拆分点对应现有 `router_engine.py` 的 `predict_chat_messages()` 方法。

### 接口定义

```
POST /internal/v1/classify
Content-Type: application/json
```

**Request**：

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "帮我写一个快速排序"}
  ],
  "request_id": "chat-abc123def456",
  "runtime_config": {
    "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
    "score_bands": {"easy": [0, 3.5], "medium": [3.5, 7.0], "hard": [7.0, 10.0]},
    "tier_model_map": {"easy": "model-a", "medium": "model-b", "hard": "model-c"}
  }
}
```

- `messages`：OpenAI 格式的聊天消息数组（必填）
- `request_id`：请求追踪 ID（可选，inference-svc 会自动生成）
- `runtime_config`：运行时路由配置覆盖（可选，不传则使用 inference-svc 默认配置）

**Response**：

```json
{
  "request_id": "chat-abc123def456",
  "scores_0_2": {
    "纠错": 0.3421,
    "工具调用": 0.1205,
    "通用任务": 0.8734,
    "任务拆解": 0.5012,
    "编程": 1.7823
  },
  "proto_weighted_0_2": 1.2345,
  "total_score_0_10": 7.8234,
  "score_source": "proto_weighted_0_2",
  "routing_tier": "hard",
  "selected_model": "model-c",
  "tier_model_map": {"easy": "model-a", "medium": "model-b", "hard": "model-c"},
  "score_bands_raw": {"easy": [0, 3.5], "medium": [3.5, 7.0], "hard": [7.0, 10.0]}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `scores_0_2` | `Dict[str, float]` | 5 维分类得分（0-2 归一化） |
| `proto_weighted_0_2` | `float \| null` | proto 语义加权后的综合分（无 proto 时为 null） |
| `total_score_0_10` | `float` | 最终综合评分（0-10） |
| `score_source` | `str` | 评分来源（`proto_weighted_0_2` 或 `runtime_weighted_0_10_fallback`） |
| `routing_tier` | `str` | 映射层级（easy / medium / hard） |
| `selected_model` | `str` | 选中的目标模型 |

---

## 6. 网络与通信

### 容器间调用关系

```
backend-app ←→ 自身 (admin↔user HMAC loopback)
backend-app ← testing-worker (HMAC: fetch_admin_by_uid)

router-service → inference-svc  (内部 HTTP: /internal/v1/classify)
router-service → upstream LLM   (外部 HTTP: litellm 转发)
router-service → user-service   (API Key 校验, via backend-app)

inference-svc：无外部调用，仅被 router-service 调用
```

### 通信方式选择

| 调用路径 | 方式 | 理由 |
|----------|------|------|
| router → inference-svc | 内网 HTTP（无 HMAC） | 纯内部服务，同一 Docker network，低延迟优先 |
| router → backend-app | HMAC 签名 HTTP | 复用现有 API Key 校验链路 |
| worker → backend-app | HMAC 签名 HTTP | 跨容器，已有机制 |
| backend-app 内部 | HMAC loopback | 保持回滚兼容 |

---

## 7. Docker Compose 草稿（三容器拓扑）

```yaml
# 三容器部署拓扑草稿
# backend-app (控制面) + router-service (CPU 网关) + inference-svc (GPU 推理)

services:

  # ── Container 1: 控制面（全部非 router 服务） ──────────────────────
  backend-app:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    container_name: backend-app
    env_file: ../.env
    restart: unless-stopped
    environment:
      ADMIN_DATABASE_URL: "${ADMIN_DATABASE_URL}"
      USER_DATABASE_URL: "${USER_DATABASE_URL}"
      TESTING_DATABASE_URL: "${TESTING_DATABASE_URL}"
      DATABASE_POOL_SIZE: "${DB_POOL_SIZE:-5}"
      DATABASE_MAX_OVERFLOW: "${DB_MAX_OVERFLOW:-10}"
      JWT_SECRET_KEY: "${JWT_SECRET_KEY}"
      INTERNAL_SECRET: "${INTERNAL_SECRET}"
      ADMIN_SERVICE_URL: "http://backend-app:8001"
      USER_SERVICE_URL: "http://backend-app:8001"
      ROUTER_SERVICE_URL: "http://router-service:8003"
      BENCHMARK_QUEUE_REDIS_URL: "redis://redis:6379/0"
      PROBE_SCHEDULER_ENABLED: "false"
    command: >
      /app/.venv/bin/uvicorn backend_app.main:app
      --host 0.0.0.0 --port 8001 --workers 2
    ports:
      - "8001:8001"
    volumes:
      - backend_logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "scripts/runtime_probe.py", "http-ready", "--port", "8001"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - eucal_network

  testing-scheduler:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    container_name: testing-scheduler
    profiles: ["scheduler"]
    env_file: ../.env
    restart: unless-stopped
    environment:
      TESTING_DATABASE_URL: "${TESTING_DATABASE_URL}"
      INTERNAL_SECRET: "${INTERNAL_SECRET}"
      ADMIN_SERVICE_URL: "http://backend-app:8001"
      BENCHMARK_QUEUE_REDIS_URL: "redis://redis:6379/0"
      PROBE_SCHEDULER_ENABLED: "true"
      PROBE_CRON_HOURS: "${PROBE_CRON_HOURS:-0,6,12,18}"
    command: >
      /app/.venv/bin/uvicorn testing_service.main:app
      --host 0.0.0.0 --port 8012 --workers 1
    depends_on:
      backend-app: { condition: service_healthy }
      redis: { condition: service_healthy }
    networks:
      - eucal_network

  testing-worker:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    container_name: testing-worker
    env_file: ../.env
    restart: unless-stopped
    environment:
      TESTING_DATABASE_URL: "${TESTING_DATABASE_URL}"
      INTERNAL_SECRET: "${INTERNAL_SECRET}"
      ADMIN_SERVICE_URL: "http://backend-app:8001"
      BENCHMARK_QUEUE_REDIS_URL: "redis://redis:6379/0"
    command: ["/app/.venv/bin/python", "-m", "arq", "testing_service.worker.WorkerSettings"]
    depends_on:
      backend-app: { condition: service_healthy }
      redis: { condition: service_healthy }
    networks:
      - eucal_network

  redis:
    image: redis:7-alpine
    container_name: testing-redis
    restart: unless-stopped
    command: ["redis-server", "--save", "", "--appendonly", "no"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - eucal_network

  # ── Container 2: router-service（CPU 网关） ───────────────────────
  router-service:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.router-cpu
    container_name: router-service
    env_file: ../.env
    restart: unless-stopped
    environment:
      ROUTER_RUNTIME_CONFIG: "/app/deploy/router/runtime_config.json"
      ROUTER_MODEL_PATHS: "/app/deploy/router/model_paths.json"
      ROUTER_LOG_DIR: "/app/logs"
      # 推理服务地址
      INFERENCE_SERVICE_URL: "http://inference-svc:8004"
      DEBUG: "${DEBUG:-false}"
    command: >
      /app/.venv/bin/uvicorn router_service.main:app
      --host 0.0.0.0 --port 8003 --workers 4
    ports:
      - "8003:8003"
    deploy:
      replicas: 2
    volumes:
      - backend_logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "scripts/runtime_probe.py", "http-ready", "--port", "8003"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
    networks:
      - eucal_network

  # ── Container 3: inference-service（GPU 推理） ────────────────────
  inference-svc:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.inference
    container_name: inference-svc
    restart: unless-stopped
    environment:
      ROUTER_MODEL_PATHS: "/app/deploy/router/model_paths.json"
      ROUTER_RUNTIME_CONFIG: "/app/deploy/router/runtime_config.json"
      INFERENCE_PORT: "8004"
      CUDA_VISIBLE_DEVICES: "0"
      DEBUG: "${DEBUG:-false}"
    command: >
      /app/.venv/bin/uvicorn inference_service.main:app
      --host 0.0.0.0 --port 8004 --workers 1
    ports:
      - "8004:8004"
    volumes:
      - backend_logs:/app/logs
      - model_weights:/app/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "python", "scripts/runtime_probe.py", "http-ready", "--port", "8004"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 120s
    networks:
      - eucal_network

networks:
  eucal_network:
    name: eucal_network
    external: true

volumes:
  backend_logs:
    name: eucal_backend_logs
  redis_data:
    name: eucal_redis_data
  model_weights:
    name: eucal_model_weights
```

---

## 8. 当前 vs 目标对照

### 现有（2 容器 + 辅助进程）

```
backend-app (:8001)     ← admin + user + testing 合并
router-service (:8003)  ← HTTP 网关 + ML 推理 一体
testing-scheduler       ← 定时调度
testing-worker          ← 队列消费
redis                   ← 队列后端
```

**问题**：router-service 绑定 GPU 依赖，扩容时每个副本都需要 GPU。

### 目标（3 容器 + 辅助进程）

```
backend-app (:8001)     ← 不变
router-service (:8003)  ← 仅 CPU 网关（去掉 torch/transformers）
inference-svc (:8004)   ← 新增，GPU 推理
testing-scheduler       ← 不变
testing-worker          ← 不变
redis                   ← 不变
```

**收益**：

| 维度 | 改进 |
|------|------|
| 扩容成本 | router-service 副本不再需要 GPU，只需 CPU/内存 |
| 镜像体积 | router 镜像从 ~2GB+（含 torch）降至 ~200MB |
| 资源利用率 | GPU 集中在 inference-svc，按推理 QPS 精确分配 |
| 故障隔离 | inference-svc 宕机时 router 可降级（直连上游），不影响控制面 |
| 开发体验 | 本地开发 router 无需安装 ML 依赖 |

### 拆分工作项

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 1 | 新建 `src/inference_service/` 模块 | `main.py`, `config.py`, `api/` |
| 2 | 将 `router_engine.py` + `nn/` + `utils/scoring.py` 等移入 | 从 `router_service` 剥离 |
| 3 | 改造 `router_service` 的路由层 | 将 `engine.predict_chat_messages()` 替换为 HTTP 调用 |
| 4 | 新增 `deploy/Dockerfile.router-cpu` | 不含 torch，轻量镜像 |
| 5 | 新增 `deploy/Dockerfile.inference` | 含 torch + CUDA，GPU 镜像 |
| 6 | 更新 `deploy/docker-compose.yml` | 三容器拓扑 |
| 7 | 更新 `pyproject.toml` 依赖分组 | `[router]` 组瘦身，新增 `[inference]` 组 |

---

## 9. 端口规划

| 端口 | 服务 | 类型 |
|------|------|------|
| 8001 | backend-app | 外部可达 |
| 8003 | router-service | 外部可达 |
| 8004 | inference-svc | 仅内网 |
| 8012 | testing-scheduler | 仅内网 |
| 6379 | redis | 仅内网 |
