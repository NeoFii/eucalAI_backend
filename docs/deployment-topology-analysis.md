# Eucal AI 部署拓扑分析

> 基于 `Frontend-zh`、`eucal-admin-main`、`backend` 三个代码仓库的实际代码调研
> 更新日期：2026-04-24 (v2: 清理 testing-api 遗留、新增模型目录网关缓存层)

---

## 一、实际拓扑总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         接入层 (Frontend)                            │
│                                                                     │
│   Frontend-zh (:3000)                     eucal-admin (:3001)       │
│   ├─ /api/* ──────→ user-service          └─ /api/* ──→ admin-svc  │
│   └─ /router-api/* → router-service (仅 OpenAI 兼容端点)            │
└──────────┬──────────────────┬──────────────────────┬────────────────┘
           │                  │                      │
           ▼                  │                      ▼
┌──────────────────────────────┼─────────────────────────────────────┐
│  Backend 节点 (10.0.0.10)    │                                     │
│                              │                                     │
│  ┌────────────────────┐      │      ┌────────────────────┐        │
│  │  user-service       │ ←─HMAC── │  admin-service       │        │
│  │  :8000              │ ──HMAC─→ │  :8001               │        │
│  │  认证/账单/Key/     │           │  管理员认证/模型目录/ │        │
│  │  调用日志/代金券/   │           │  路由配置/审计日志    │        │
│  │  模型目录(网关)     │           │                      │        │
│  └────────┬───────────┘           └────────┬────────────┘        │
│           │                                │                      │
│           ▼                                ▼                      │
│  MySQL eucal_ai_user              MySQL eucal_ai_admin            │
│                                                                    │
│  Redis :6379/0 (JWT黑名单)    Redis :6379/1 (任务队列)             │
│  Redis :6379/2 (模型目录缓存)        │                             │
│                                      │                             │
│                                      ▼                             │
│                              user-worker (arq)                     │
└────────────────────────────────────────────────────────────────────┘
                    ▲         ▲                    ▲
               HMAC │    HMAC │               HMAC │
                    │         │                    │
┌───────────────────┴─────────┴────────────────────┴─────────────────┐
│  Router 节点 (独立机器, CPU)                                        │
│                                                                     │
│  router-service (:8003)                                             │
│  公网 API 网关 — OpenAI 兼容接口 (/v1/chat/completions, /v1/models)│
│                                                                     │
│  出站调用:                                                          │
│    ──HMAC──→ user-service   (API Key 验证, 调用日志写入)            │
│    ──HMAC──→ admin-service  (路由配置拉取, 每60s轮询)               │
│    ──Secret─→ inference-svc (难度分类, X-Inference-Secret)          │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │
                        Secret    │
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│  GPU 节点 (10.0.0.20)                                              │
│                                                                    │
│  inference-service (:8004)                                         │
│  Qwen2.5-7B backbone + 5x CG-TabM 分类头                          │
│                                                                    │
│  出站调用:                                                         │
│    ──HMAC──→ admin-service  (路由配置刷新, 每60s轮询)              │
└────────────────────────────────────────────────────────────────────┘
```

---

## 二、服务节点清单

| 服务 | 端口 | 数据库 | 部署位置 | 职责 |
|------|------|--------|---------|------|
| Frontend-zh | 3000 | — | 前端 | 官网：注册/登录/控制台/充值/API Key/模型目录 |
| eucal-admin | 3001 | — | 前端 | 管理端：管理员登录/用户管理/模型目录/路由配置/代金券 |
| user-service | 8000 | MySQL `eucal_ai_user` | 10.0.0.10 | 用户认证、账单、API Key 管理、调用日志、代金券兑换、模型目录网关(缓存) |
| admin-service | 8001 | MySQL `eucal_ai_admin` | 10.0.0.10 | 管理员认证、模型目录、路由配置、审计日志、代金券发放 |
| user-worker | — | MySQL + Redis | 10.0.0.10 | arq 异步任务消费者 |
| router-service | 8003 | 无 | 独立机器 (CPU) | 公网 API 网关：OpenAI 兼容接口、智能路由、难度分类调度 |
| inference-service | 8004 | 无 | 10.0.0.20 (GPU) | ML 推理：输入难度分类 → 模型分级路由 |

---

## 三、前端 → 后端连接关系

### 3.1 Frontend-zh (官网, :3000)

| 代理路径 | 目标服务 | 实际用途 | 配置文件 |
|---------|---------|---------|---------|
| `/api/:path*` → `:8000` | user-service | 认证、账单、API Key、调用日志、代金券、模型目录(网关) | `next.config.mjs` + `proxy-config.js` |
| `/router-api/:path*` → `:8003` | router-service | 仅 OpenAI 兼容端点 (`/v1/chat/completions`, `/v1/models`) | `next.config.mjs` + `proxy-config.js` |

关键细节：
- 前端 `router.ts` 中的账单/Key 相关 API（`/keys`, `/billing/*`）全部通过 `/api/v1` 前缀调用，走的是 user-service (:8000)，不是 router-service (:8003)。Router-service 对前端仅暴露 OpenAI 兼容的推理接口。
- 模型目录数据由 admin-service 管理，user-service 通过 HMAC 网关代理读取并缓存到 Redis db/2（TTL 120-300s），前端统一通过 `/api/v1/model-catalog/*` 访问 user-service。

### 3.2 eucal-admin (管理端, :3001)

| 代理路径 | 目标服务 | 实际用途 | 配置文件 |
|---------|---------|---------|---------|
| `/api/:path*` → `:8001` | admin-service | 全部管理操作（管理员认证、用户管理、模型目录、路由配置、代金券、审计日志） | `next.config.mjs` |

管理端仅连接 admin-service 一个后端。

---

## 四、服务间调用关系（全部单向）

### 4.1 HMAC-SHA256 签名调用

协议：`X-Internal-Service` + `X-Internal-Timestamp` + `X-Internal-Signature`
共享密钥：`INTERNAL_SECRET`
实现：`src/common/internal.py`
防护：30s 时间戳 TTL + 熔断器 (3次失败/30s冷却) + 重试

| 调用方 | → | 被调用方 | 端点 | 用途 |
|--------|---|---------|------|------|
| router-service | → | user-service | `POST /api/v1/internal/api-keys/validate` | API Key 验证 |
| router-service | → | user-service | `POST /api/v1/internal/call-logs` | 调用日志创建 |
| router-service | → | user-service | `PATCH /api/v1/internal/call-logs/{id}` | 调用日志更新 |
| router-service | → | admin-service | `GET /api/v1/internal/routing-config/active/full` | 路由配置拉取 (60s轮询) |
| admin-service | → | user-service | `GET/POST /api/v1/internal/users/*` | 用户管理全套操作 |
| admin-service | → | user-service | `POST/GET /api/v1/internal/vouchers/*` | 代金券管理 |
| admin-service | → | user-service | `GET /api/v1/internal/usage/*` | 使用统计 |
| user-service | → | admin-service | `GET /api/v1/internal/model-catalog/vendors` | 模型供应商列表 (缓存 300s) |
| user-service | → | admin-service | `GET /api/v1/internal/model-catalog/categories` | 模型分类列表 (缓存 300s) |
| user-service | → | admin-service | `GET /api/v1/internal/model-catalog/models` | 模型列表 (缓存 120s) |
| user-service | → | admin-service | `GET /api/v1/internal/model-catalog/models/{slug}` | 模型详情 (缓存 300s) |
| inference-service | → | admin-service | `GET /api/v1/internal/routing-config/active/inference` | 路由配置刷新 (60s轮询) |

### 4.2 共享密钥比对

协议：`X-Inference-Secret` 头，简单 `hmac.compare_digest` 比对
独立密钥：`INFERENCE_SERVICE_SECRET`
实现：`src/inference_service/auth.py`

| 调用方 | → | 被调用方 | 端点 | 用途 |
|--------|---|---------|------|------|
| router-service | → | inference-service | `POST /internal/v1/classify` | 输入难度分类 |

---

## 五、部署架构（Docker Compose 三机拆分）

```
Machine 1 — Backend (10.0.0.10)
├── docker-compose.backend.yml
├── MySQL 8.0 (eucal_ai_admin + eucal_ai_user, 同实例不同库)
├── Redis 7 Alpine
├── user-service (:8000, 2 workers)
├── admin-service (:8001, 2 workers)
└── user-worker (arq consumer, 依赖 MySQL + Redis)

Machine 2 — Router (独立机器, CPU)
├── docker-compose.router.yml
└── router-service (:8003, 4 workers)
    ├── USER_SERVICE_URL=http://10.0.0.10:8000
    ├── ADMIN_SERVICE_URL=http://10.0.0.10:8001
    └── INFERENCE_SERVICE_URL=http://10.0.0.20:8004

Machine 3 — GPU (10.0.0.20)
├── docker-compose.inference.yml
└── inference-service (:8004, 1 worker, 1x NVIDIA GPU)
    ├── ADMIN_SERVICE_URL=http://10.0.0.10:8001
    └── 模型权重挂载: /srv/eucal/models → /app/models:ro
```

另有 `docker-compose.local-infra.yml` 提供本地开发用 MySQL (:3307) + Redis (:6380)。

---

## 六、与原始拓扑设计的对比

### 匹配项

| # | 原始描述 | 验证结果 |
|---|---------|---------|
| 1 | 管理端 ↔ Admin-Service | 匹配 — `eucal-admin-main/next.config.mjs` 仅代理到 `:8001` |
| 2 | Admin-Service ↔ Admin-Database | 匹配 — `eucal_ai_admin` |
| 3 | User-Service ↔ User-Database | 匹配 — `eucal_ai_user` |
| 4 | Router-Service 无数据库 | 匹配 — 无任何 DB 配置 |
| 5 | Router → GPU-Service 任务分发 | 匹配 — `inference_client.py` 调用 `/internal/v1/classify` |
| 6 | 五层架构分层 | 基本匹配 — 接入/业务/调度/计算/存储 |

### 不一致项

| # | 原始描述 | 实际情况 |
|---|---------|---------|
| 1 | 官网仅连 User-Service | 官网还连 router-service（OpenAI 兼容端点），但账单/Key 确实走 user-service |
| 2 | User-Service ↔ Router-Service 双向 HMAC | 单向：Router → User-Service。User-Service 无任何对 Router 的出站调用（但有 → Admin-Service 的模型目录网关调用） |
| 3 | Admin-Service ↔ Router-Service 双向 HMAC | 单向：Router → Admin-Service。Admin-Service 无对 Router 的出站调用 |
| 4 | Router 与 GPU-Service 在同一椭圆封闭域 | 部署在不同机器 — Router 独立机器 vs Inference 在 10.0.0.20 |
| 5 | Router ↔ GPU-Service 双向通信 | 单向：Router → Inference。Inference 的出站调用只有 → Admin-Service |
| 6 | 所有跨服务调用统称 HMAC | 两种机制：HMAC-SHA256 签名 (大部分) + 简单共享密钥 (Router→Inference) |

### 缺失项

| # | 缺失组件 | 说明 |
|---|---------|------|
| 1 | Inference → Admin-Service | inference-service 通过 HMAC 定期拉取路由配置 |
| 2 | Redis | JWT 黑名单 (:6379/0) + 异步任务队列 (:6379/1) + 模型目录缓存 (:6379/2) |
| 3 | user-worker | arq 异步任务消费进程 |
| 4 | ~~testing-service 代理~~ | 已清理 — Frontend-zh 的 `/testing-api` 代理和相关死代码已移除 |

---

## 七、Router-Service 路由流程

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
  ├─ 3. 查找模型对应的上游 provider (autodl/aiping/openrouter)
  │
  ├─ 4. litellm.acompletion → 上游 LLM API
  │
  └─ 5. HMAC → user-service: 写入调用日志 + 扣费
```

路由配置来源（三级降级）：
1. admin-service（HMAC 拉取，60s 轮询）
2. 上次成功的缓存配置
3. 本地 `deploy/router/runtime_config.json`
