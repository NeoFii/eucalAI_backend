# 三部署单元架构收敛：清理历史漂移 + GPU 推理解耦

> 项目内实施单据。规划源文件：`C:\Users\luofei\.claude\plans\todo-md-merry-teacup.md`
> 创建日期：2026-04-19
> 范围扩展：2026-04-19（追加 Phase 2 · GPU Pool 解耦）

## 进度追踪

### Phase 1 · 历史漂移清理

| # | 任务 | 状态 | Commit / PR | 备注 |
|---|---|---|---|---|
| T0 | 落地 TODO.md | ✅ | — | 本文件 |
| T1 | 验证 Dockerfile D4 真实影响 | ⬜ | | 仍需跑，指导 T13 细节 |
| T2 | 消除 D1(router DB env) | ⬜ | | |
| T3 | 消除 D2(router schema 残留) | ⬜ | | |
| T4 | 消除 D3(`/internal/router/*` 死端点) | ⬜ | | |
| T5 | 清理 `ROUTER_SERVICE_URL` 等未使用变量 | ⬜ | | |

### Phase 2 · GPU Pool 解耦

| # | 任务 | 状态 | Commit / PR | 备注 |
|---|---|---|---|---|
| T10 | 定义 GPU Pool HTTP 接口契约 + schemas | ⬜ | | 方案 B |
| T11 | 新建 `src/gpu_pool/` 包骨架 | ⬜ | | 复用现有 logging |
| T12 | 搬迁 ML 代码到 gpu_pool | ⬜ | | nn/、router_engine、model_paths |
| T13 | Dockerfile 三拆（control-plane + router + gpu-pool） | ⬜ | | 替代原 T7 |
| T14 | router-service 改造：`engine.route()` → HTTP 调 Pool | ⬜ | | 包含错误/超时处理 |
| T15 | docker-compose 三容器编排 + GPU 资源声明 | ⬜ | | |
| T16 | 日志链路重设计 + 新增契约测试 | ⬜ | | routing.jsonl 归属 |

### Phase 3 · 收尾

| # | 任务 | 状态 | Commit / PR | 备注 |
|---|---|---|---|---|
| T17 | 更新 `docs/ARCHITECTURE.md` | ⬜ | | 三部署单元拓扑 |
| T18 | 全量 harness run | ⬜ | | 出 PR 前总门禁 |

---

## Context

### 为什么做这件事

目标架构是 **三个可部署单元**：

```
控制面 (1 机)                router-service (N 机, CPU)      GPU Pool (M 机, GPU)
backend-app                  ┌─────────────────────────┐     ┌──────────────────────┐
  admin/user/content/testing │ HTTP 入口                │     │ Qwen backbone (出注意力头)│
testing-scheduler            │ 调 GPU Pool 取分数       │ →→→ │ + 5 个路由头 (cg_tabm/proto)│
testing-worker               │ 用 runtime_config 做 tier│ ←←← │                      │
                             │ 调上游 LLM               │     │ 返回 scores + proto  │
                             │ 写 upstream.jsonl        │     │ 只做 ML 推理         │
                             └─────────────────────────┘     └──────────────────────┘
```

**收益**：

- **ML 依赖隔离**：torch / transformers ≈ 1-2GB 只在 GPU Pool 镜像，router-service 镜像从 ~3-5GB 降到 <500MB
- **扩容维度独立**：CPU-bound 的路由链路（router-service）和 GPU-bound 的推理（Pool）各自按真实负载扩
- **GPU 池化**：多个 router-service 副本可共享一组 GPU，利用率显著上升
- **模型热更新**：换权重只重启 Pool，router-service 链路不动
- **历史漂移清理**：先把现存的 5 处代码/测试/文档不一致修掉，再做解耦，防止"在已经错的地基上又建一层"

### 已确认的关键决策（2026-04-19）

- **决策 1 · Dockerfile 拆分**：拆成三个文件 `deploy/Dockerfile.control-plane` + `deploy/Dockerfile.router` + `deploy/Dockerfile.gpu-pool`（原计划的两拆升级）。→ 对应 **T13**
- **决策 2 · 死端点 `/api/v1/internal/router/*`**：grep 验证无调用方后直接删除。→ 对应 **T4**
- **决策 3 · 未使用变量清理**：`ROUTER_SERVICE_URL` 字段和 `docker-compose.yml` 中 backend-app 的 `ROUTER_SERVICE_URL` 注入一并清掉。→ 对应 **T5**
- **决策 4 · GPU Pool 接口 = 方案 B**：GPU Pool 吐**原始分数**（`scores_0_2`、`proto_weighted_0_2` 等 ML 输出），router-service 用 `runtime_config.json` 做 tier 映射和上游模型选择。ML 只管 ML，单一职责。→ 对应 **T10**
- **决策 5 · 配置文件归属**：
  - `deploy/router/model_paths.json` → **GPU Pool 独占**（列 Qwen backbone 路径 + 5 个路由头权重路径）
  - `deploy/router/runtime_config.json` → **router-service 独占**（tier 映射 / 上游模型列表 / 阈值）
- **决策 6 · 暂按单台 GPU 机器规划**：先不做 GPU Pool 多副本 LB，router-service 配 1 个 `GPU_POOL_URL`；未来扩时再选 Nginx / K8s Service 方案。→ 记入"非目标"
- **决策 7 · 先做 Phase 1 再做 Phase 2，但本单据一次性规划**：两阶段可以分 PR 推进，但 TODO.md 从一开始就完整列出避免"先清理完发现架构又要动"

---

## 当前边界快照（调研产出）

### backend-app 内部子域

| 子域 | 包路径 | Settings 类 | DATABASE_URL env | Snowflake WorkerID | Port（独立模式）|
|---|---|---|---|---|---|
| admin | `src/admin_service/` | `admin_service.config.Settings` | `ADMIN_DATABASE_URL` | 2 | 8001 |
| user | `src/user_service/` | `user_service.config.Settings` | `USER_DATABASE_URL` | 1 | 8000 |
| content | `src/content_service/` | `content_service.config.Settings` | `CONTENT_DATABASE_URL` | 5 | 8004 |
| testing | `src/testing_service/` | `testing_service.config.Settings` | `TESTING_DATABASE_URL` | 3 | 8002 |
| backend-app | `src/backend_app/` | `backend_app.config.BackendAppSettings` | （持 4 个） | 1 | 8001 |
| router | `src/router_service/` | ❌ 不用 `BaseServiceSettings` | ❌ 无 DB | — | 8003 |
| **gpu-pool**（规划） | `src/gpu_pool/` | ❌ 不用 `BaseServiceSettings` | ❌ 无 DB | — | **8014**（建议） |

所有子域的 `Settings` 都继承 `common.config.BaseServiceSettings`（`src/common/config.py:9`），共享 `JWT_SECRET_KEY` / `INTERNAL_SECRET` 校验。**router 和规划中的 gpu-pool 都是例外**，它们自己的 `config.py` 只有常量和配置加载逻辑，根本不走 pydantic-settings。

### 路由前缀归属（`backend_app/main.py` 聚合）

| 前缀 | 归属 | 说明 |
|---|---|---|
| `/api/v1/admin/auth/*` | admin public | 重挂到 `/admin` 避让 user 的 `/auth` |
| `/api/v1/admin-users/*` | admin public | |
| `/api/v1/admin-audit-logs/*` | admin public | |
| `/api/v1/invitation-codes/*` | admin public | |
| `/api/v1/dashboard/*` | admin public | 通过 `invitation.py` 提供 |
| `/api/v1/internal/admins/*` | admin internal | HMAC；被 content、testing 调用 |
| `/api/v1/internal/invitation-codes/*` | admin internal | HMAC；被 user 调用 |
| `/api/v1/auth/*` | user public | 面向终端用户 |
| `/api/v1/internal/users/*` | user internal | HMAC；被 admin-service 调用 |
| `/api/v1/internal/router/*` | **testing internal** | ⚠️ 旧 router 遗留端点，新 router 不调用（T4 删除） |
| `/api/v1/news/*` | content public | user 的 news 代理被故意剔除 |
| `/api/v1/models/*` 等 testing 面 | testing public | |

### 跨服务 HMAC 客户端调用链（当前 5 条）

| Caller | 客户端文件 | 调用的目标路径 | 调用方法 |
|---|---|---|---|
| user | `user_service/services/admin_client.py:30` | `POST /api/v1/internal/invitation-codes/consume` | `post_internal_json` |
| user | `user_service/services/admin_client.py:56` | `POST /api/v1/internal/invitation-codes/release` | `post_internal_json` |
| admin | `admin_service/services/identity_client.py:19` | `GET /api/v1/internal/users/{uid}` | `get_internal_json` |
| content | `content_service/services/admin_identity_client.py:35` | `GET /api/v1/internal/admins/{uid}` | `get_internal_json` |
| testing | `testing_service/services/admin_identity_client.py:37` | `GET /api/v1/internal/admins/{uid}` | `get_internal_json` |

**新规划**：router-service → GPU Pool 是 **第 6 条**跨进程调用。不走 HMAC（GPU Pool 内部服务，无敏感身份逻辑），但需要简单 shared-secret 防止外部直连 Pool。详见 T10。

### router-service 当前独立性验证

- ✅ 代码零跨包 import
- ✅ `router_service/main.py` 只从 `deploy/router/` 读配置，三个 env 可覆盖
- ✅ `require_api_key` 自包含，不调 DB 不调其他服务
- ✅ docker-compose 的 router-service env 不注入 DB/JWT/INTERNAL_SECRET
- ✅ 没有任何子域调用 router 的内部端点

### 控制面三进程协作

| 进程 | 入口 | Port | 依赖 | 共享状态 |
|---|---|---|---|---|
| backend-app | `backend_app.main:app` | 8001 | 4 个 MySQL schema | 挂载 testing api router；不启动 apscheduler |
| testing-scheduler | `testing_service.main:app` | 8012 | testing DB + Redis | 与 backend-app 共用代码，`PROBE_SCHEDULER_ENABLED=true` 时激活 |
| testing-worker | `arq testing_service.worker.WorkerSettings` | 无 HTTP | testing DB + Redis | 任务由 backend-app benchmark API 入队 |

### 关键测试 gate（harness 基础）

| 测试文件 | 守护目标 |
|---|---|
| `tests/test_backend_app.py` | `(method, path)` 路由唯一；必有内部端点；health/ready 可达 |
| `tests/test_schema_ownership.py` | docs 与 SQL 快照一致；**⚠️ 仍要求 router 三张表**（T3 清） |
| `tests/test_schema_drift.py` | ORM metadata ↔ SQL 快照完全一致 |
| `tests/test_internal_contracts.py` | HMAC 签名协议；**⚠️ 含 `/internal/router/*` 断言**（T4 清） |
| `tests/test_runtime_orchestration.py` | compose 用 `/ready`；Dockerfile EXPOSE；start_services 认 scheduler |
| `tests/test_service_environment.py` | 必需 env；禁共享 DB URL；**⚠️ 仍设 `ROUTER_DATABASE_URL`**（T2 清） |
| `tests/test_runtime_probe.py` | `http-ready` / `worker-ready` CLI |

---

## 历史漂移清单

| # | 漂移现象 | 代码证据 | 事实 |
|---|---|---|---|
| **D1** | `check_service_environment.py` 要求 `ROUTER_DATABASE_URL` | `scripts/check_service_environment.py:23` | router 无 DB 调用 |
| **D2** | schema-ownership 测试 + SQL 快照仍含 router 三表 | `tests/test_schema_ownership.py:10-25`；`scripts/sql/router_schema.sql` 存在 | router 无 ORM、无 migrations |
| **D3** | `/api/v1/internal/router/*` 仍挂载 | `src/testing_service/api/v1/endpoints/internal_router.py`；`test_backend_app.py:72` | 新 router 不调；无调用方 |
| **D4** | Dockerfile 无 `--extra router`；镜像含所有包 | `deploy/Dockerfile:18,33-39` | router 容器启动会在 import torch 失败 |
| **D5** | Dockerfile `EXPOSE` 含废弃端口 | `deploy/Dockerfile:52` `EXPOSE 8000 8001 8002 8003 8004 8012` | 实际只用 8001/8003/8012 |
| **D6**（新）| ML 推理与路由决策仍耦合在同一进程 | `src/router_service/nn/`、`services/router_engine.py` | 应拆到 GPU Pool 独立部署 |

---

## 改动约束 harness（每次改动必须过的门禁）

**铁律：任何改动 PR 合并前，以下全部绿灯。**

### L0 必跑（每次 commit）

| 命令 | 防的是什么 |
|---|---|
| `uv run ruff check .` | 格式/语法回退 |
| `uv run pytest tests/test_backend_app.py` | 路由唯一性、内部端点存在 |
| `uv run pytest tests/test_schema_ownership.py tests/test_schema_drift.py` | ORM ↔ SQL ↔ docs 一致 |
| `uv run pytest tests/test_internal_contracts.py` | HMAC 协议不能破 |
| `uv run pytest tests/test_service_environment.py tests/test_runtime_probe.py tests/test_runtime_orchestration.py` | 启动脚本/Dockerfile/compose/env 协同 |

### L1 阶段性 checkpoint

| 命令 | 防的是什么 |
|---|---|
| `uv run pytest`（全量）| 基线 168 passed / 7 skipped，不允许新增 skip |
| `uv run check-env` | 真实 env 能过校验 |
| `uv run bootstrap-databases` | 4 库 upgrade head |
| `uv run start`（本地冒烟）| 4 进程能起、`/ready` 200 |

### L2 部署前（三部署单元）

| 验证 | 防的是什么 |
|---|---|
| `docker compose build backend-app` | 控制面镜像无 torch |
| `docker compose build router-service` | router 镜像 <500MB，无 torch |
| `docker compose build gpu-pool` | GPU Pool 镜像含 torch / transformers |
| `docker compose up` 三容器起 | 三者 `/ready` 都 200 |
| **新增 L2 契约测试**：`docker compose up` 后 `curl -X POST gpu-pool:8014/classify` 返回合法 schema | GPU Pool 接口契约不破 |
| **新增 L2 端到端**：`curl -X POST router-service:8003/v1/chat/completions` 看日志链 `router → pool → upstream` 闭合 | 链路不断 |

### 基线快照

- 测试基线：**168 passed / 7 skipped**
- 6 个整文件 skip 的旧测试**保持 skip**
- 禁止删除任何未列出的测试文件

---

## Phase 1 · 历史漂移清理（T1–T5）

### T1 · 验证 Dockerfile D4 的真实影响（只读，不改任何文件）

- **动作**：本地 `docker compose build router-service` → `docker compose up router-service`，观察是否 `ModuleNotFoundError`（numpy/torch/transformers）；记录 traceback
- **产物**：验证记录贴 PR 描述
- **不管结果如何**：最终 T13 都会三拆 Dockerfile，这里只是确认 D4 性质

### T2 · 消除漂移 D1（router DB env 要求）

- **文件**：`scripts/check_service_environment.py:23`
- **改动**：
  - 从 `SERVICE_DATABASE_ENV` 删除 `router-service` 条目
  - `validate_environment` 处理 `router-service` 时走**无 DB 分支**（只检查 common secret）
  - 同时新增 `gpu-pool` 条目，也走**无 DB 分支**（为 Phase 2 铺路）
- **测试同步**：`tests/test_service_environment.py:103-115` 重写为"router-service / gpu-pool 不要求 DB URL"
- **验证**：`uv run pytest tests/test_service_environment.py -v` 全绿

### T3 · 消除漂移 D2（router schema 残留）

- **改动**：
  - 删除 `scripts/sql/router_schema.sql`
  - `scripts/sql/init_tables.sql` 去掉 router 的 SOURCE 行
  - `docs/schema-ownership.md` 删除 router-service 段落
  - `tests/test_schema_ownership.py`：删除 `SERVICE_OWNED_OBJECTS["router"]`；对应断言同步去除
- **验证**：`uv run pytest tests/test_schema_ownership.py tests/test_schema_drift.py -v` 全绿

### T4 · 消除漂移 D3（死端点 `/api/v1/internal/router/*`）

- **预检查（只读）**：
  - `grep -R "internal/router" src/ tests/` —— 期望只在定义处和测试里出现
  - `grep -R "router_engine_client\|router_catalog_client" src/` —— 期望 0 条
- **确认无调用方后**：
  - 删除 `src/testing_service/api/v1/endpoints/internal_router.py`
  - `testing_service/api/v1/router.py` 去掉 `internal_router` include
  - `tests/test_backend_app.py:72` 删对应断言
  - `tests/test_internal_contracts.py`：删除 `_build_testing_internal_router_app`、两个 `test_testing_internal_router_*` 用例
- **验证**：`uv run pytest tests/test_backend_app.py tests/test_internal_contracts.py -v` 全绿

### T5 · 清理 `ROUTER_SERVICE_URL` 等未使用变量

- **动作**：
  - 删除 `user_service/config.py:26` 的 `ROUTER_SERVICE_URL` 字段
  - 删除 `docker-compose.yml` backend-app 环境中的 `ROUTER_SERVICE_URL` 注入
- **注意**：Phase 2 会新增 `GPU_POOL_URL`，别搞混
- **验证**：`uv run pytest` 全量

---

## Phase 2 · GPU Pool 解耦（T10–T16）

### T10 · 定义 GPU Pool HTTP 接口契约

**唯一业务端点**：`POST /classify`

**Request schema**：
```json
{
  "request_id": "req-abc",
  "messages": [{"role": "user", "content": "..."}],
  "requested_model": "auto"
}
```

**Response schema（方案 B · 原始分数）**：
```json
{
  "request_id": "req-abc",
  "scores_0_2": {
    "纠错": 0.92,
    "工具调用": 1.43,
    "通用任务": 0.78,
    "任务拆解": 1.12,
    "编程": 0.65
  },
  "proto_weighted_0_2": 1.21,
  "total_score_0_10": 6.05,
  "score_source": "proto_weighted_0_2",
  "latency_ms": 42.1,
  "backbone_version": "qwen-0.5b-router-v1"
}
```

**辅助端点**：
- `GET /health` / `GET /ready`（模型加载完成才 ready）
- `GET /v1/pool/info`：返回当前加载的模型版本、设备（cuda:0）、内存占用

**约束**：
- 不暴露 public API，仅被 router-service 调用
- 简单 shared secret 头 `X-Pool-Auth: <GPU_POOL_SECRET>`；router-service 和 GPU Pool 共享此 env
- 超时默认 5s（ML 推理典型 <200ms，5s 给足余量）

**产物**：
- `src/gpu_pool/schemas.py` —— pydantic schemas
- 在本 TODO 顶部 appendix 记录"接口 v1"契约，改接口必须升 version
- **验证**：新建 `tests/test_gpu_pool_contract.py` 测 schema 往返

### T11 · 新建 `src/gpu_pool/` 包骨架

- **目录结构**：
```
src/gpu_pool/
  __init__.py
  main.py              FastAPI app + lifespan（加载模型）
  config.py            端口、model_paths 路径、shared secret
  schemas.py           Request/Response（T10 定义）
  routers/
    __init__.py
    classify.py        POST /classify
    meta.py            /health /ready /v1/pool/info
  services/
    __init__.py
    inference.py       包装 HybridIntegratedDifficultyRouter（从 router_engine 搬）
  logging.py           复用 router_service/logging 的 JSONL 模式，但只写 routing.jsonl
```

- **端口**：8014（避开 8013 以防和 `DEFAULT_SERVICE_PORT` 默认值混淆）
- **环境变量**：
  - `GPU_POOL_MODEL_PATHS`（默认 `deploy/router/model_paths.json`，后续可迁到 `deploy/gpu_pool/`）
  - `GPU_POOL_LOG_DIR`
  - `GPU_POOL_SECRET`
  - `GPU_POOL_DEVICE`（默认 `cuda:0`，也支持 `cpu` 用于 CI）
- **产物**：空骨架能起，`/health` 200
- **验证**：`uvicorn gpu_pool.main:app` 本地启动成功

### T12 · 搬迁 ML 代码到 gpu_pool

- **搬迁清单**：
  - `src/router_service/nn/` → `src/gpu_pool/nn/`（cg_tabm.py、probe.py 及 `__init__.py`）
  - `src/router_service/services/router_engine.py` 中 `HybridIntegratedDifficultyRouter` 类 → `src/gpu_pool/services/inference.py`
  - `src/router_service/config.py` 中 `ModelPathsConfig` 和 `load_model_paths` → `src/gpu_pool/config.py`
  - `FIVEWAY_*` / `PROTO_*` / `NORMALIZE_RANGES` / `FINAL_SCORE_*` 常量 → `src/gpu_pool/config.py`（GPU Pool 需要用来出原始分数）
- **router-service 保留**：
  - `src/router_service/routers/` 全部
  - `src/router_service/services/upstream.py`（上游 LLM 调用）
  - `src/router_service/utils/runtime_config.py`（tier 映射用）
- **pyproject.toml**：
  - `[project.optional-dependencies].router` 重命名为 `[project.optional-dependencies].gpu-pool`（含 numpy/torch/transformers/sklearn/pandas）
  - router-service 改为只装基础依赖（fastapi/httpx/pydantic 已在主依赖里）
- **hatch 打包**：`[tool.hatch.build.targets.wheel].packages` 加 `src/gpu_pool`
- **验证**：
  - `python -c "from gpu_pool.services.inference import HybridIntegratedDifficultyRouter"` 成功（需 `uv sync --extra gpu-pool`）
  - `python -c "import router_service"` 成功**且不需要** `--extra gpu-pool`

### T13 · Dockerfile 三拆（替代原 T7）

三个 Dockerfile：

#### 13a · `deploy/Dockerfile.control-plane`
- Builder：`uv sync --frozen --no-dev`
- COPY：`src/common/`、`src/admin_service/`、`src/user_service/`、`src/content_service/`、`src/testing_service/`、`src/backend_app/`、`scripts/`、`pyproject.toml`
- **不 COPY**：`src/router_service/`、`src/gpu_pool/`、`deploy/router/`
- CMD：backend-app
- EXPOSE：8001 8012

#### 13b · `deploy/Dockerfile.router`
- Builder：`uv sync --frozen --no-dev`（**注意**：不再需要 `--extra gpu-pool`，router 本身不再用 ML 依赖）
- COPY：`src/router_service/`、`scripts/runtime_probe.py`、`deploy/router/runtime_config.json`、`pyproject.toml`
- **不 COPY**：`src/common/`（router 不 import）、`src/gpu_pool/`、`deploy/router/model_paths.json`
- CMD：router-service
- EXPOSE：8003

#### 13c · `deploy/Dockerfile.gpu-pool`
- Builder：`uv sync --frozen --no-dev --extra gpu-pool`（装 torch/transformers/numpy/pandas/sklearn）
- Base image：`nvidia/cuda:12.x-runtime-ubuntu22.04`（需要 CUDA runtime；如开发机无 GPU 可建 `Dockerfile.gpu-pool.cpu` 变体用 `python:3.11-slim`）
- COPY：`src/gpu_pool/`、`scripts/runtime_probe.py`、`deploy/router/model_paths.json`（搬迁后可改到 `deploy/gpu_pool/`）
- **不 COPY**：`src/common/`、`src/router_service/`
- CMD：`uvicorn gpu_pool.main:app --port 8014`
- EXPOSE：8014
- 额外：模型权重文件挂 volume `/models`（由部署时注入，镜像不内置权重以免过大）

#### 13d · 同步测试
- `tests/test_runtime_orchestration.py:19-22`：断言三个 Dockerfile 存在 + 各自关键字
- `tests/test_internal_contracts.py:920-935`：读三个 Dockerfile 分别断言
- 原 `deploy/Dockerfile` **删除**（不保留别名，避免混淆）

### T14 · router-service 改造：`engine.route()` → HTTP 调 Pool

- **新增** `src/router_service/services/gpu_pool_client.py`：
  - 用 `httpx.AsyncClient`，超时 5s，重试 1 次（短路径 ML 推理不宜多重试）
  - 带 `X-Pool-Auth` 头
  - 失败 →`ServiceUnavailableException`（沿用 `common.core.exceptions`）；但 router-service 为了不依赖 common，可以自己定义一个轻量异常类，或在 T14 顺便决定 router 是否允许 import common
  - 暴露 `async def classify(request_id, messages, requested_model) -> ClassifyResponse`
- **改造** `src/router_service/routers/chat.py` / `completions.py`：
  - 原来调 `get_router_engine().route(...)` 的地方改为调 `gpu_pool_client.classify(...)`
  - 拿到 `scores_0_2` + `proto_weighted_0_2` 后，本地用 `RuntimeConfigStore` + `runtime_config.json` 做 tier 映射，选出 `selected_model`
  - 继续调 `upstream.py` 打上游 LLM
- **删除** `src/router_service/dependencies.py::init_globals` 中的 `HybridIntegratedDifficultyRouter` 初始化；`get_router_engine` 函数整个删掉
- **保留** `RuntimeConfigStore`（tier 映射仍在 router 这边）
- **env**：新增 `GPU_POOL_URL`（默认 `http://gpu-pool:8014`）+ `GPU_POOL_SECRET`
- **验证**：现有 `/v1/chat/completions` 端点的契约测试（如 tests/test_router*.py 中还能跑的）仍绿

### T15 · docker-compose 三容器编排

在 `deploy/docker-compose.yml` 中：
- **backend-app / testing-worker / testing-scheduler** 全部用 `Dockerfile.control-plane`
- **router-service** 用 `Dockerfile.router`；env 新增 `GPU_POOL_URL=http://gpu-pool:8014` + `GPU_POOL_SECRET`
- **新增 gpu-pool 服务**：
```yaml
gpu-pool:
  build:
    context: ..
    dockerfile: deploy/Dockerfile.gpu-pool
  container_name: gpu-pool
  environment:
    GPU_POOL_MODEL_PATHS: "/app/deploy/router/model_paths.json"
    GPU_POOL_LOG_DIR: "/app/logs"
    GPU_POOL_SECRET: "${GPU_POOL_SECRET}"
    GPU_POOL_DEVICE: "cuda:0"
  volumes:
    - gpu_pool_logs:/app/logs
    - ${GPU_MODEL_WEIGHTS_DIR:-./models}:/models:ro
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  healthcheck:
    test: ["CMD", "python", "scripts/runtime_probe.py", "http-ready", "--port", "8014"]
```
- router-service `depends_on: gpu-pool: { condition: service_healthy }`
- **验证**：`docker compose up` 三容器 healthy，`curl gpu-pool:8014/ready` 200

### T16 · 日志链路重设计 + 契约测试

- **日志归属**：
  - `routing.jsonl` 拆两半：
    - GPU Pool 写"模型侧决策"（scores、proto_weighted、backbone_version、inference_latency）
    - router-service 写"路由侧决策"（request_id、requested_model、tier_mapping_result、selected_model），关联字段是 `request_id`
  - `upstream.jsonl` 继续由 router-service 独占
  - `app.log` 两个服务各自有
- **新增测试** `tests/test_gpu_pool_contract.py`：
  - `/classify` 请求缺 `X-Pool-Auth` → 403
  - `/classify` 合法请求 → schema 匹配（Pydantic 验证）
  - GPU Pool Mock：`inference.py` 注入 fake 推理结果，验证 request_id 透传
- **新增测试** `tests/test_router_calls_pool.py`：
  - Mock `gpu_pool_client.classify`，验证 `/v1/chat/completions` 会正确解析 scores → 查 runtime_config → 得到 selected_model
  - Mock 失败：GPU Pool 500 时 router-service 返回 503
- **验证**：`uv run pytest tests/test_gpu_pool_contract.py tests/test_router_calls_pool.py -v` 全绿

---

## Phase 3 · 收尾（T17–T18）

### T17 · 更新 `docs/ARCHITECTURE.md`

- §1 总体架构：改为**三部署单元**拓扑图
- §2 服务清单：加 gpu-pool 一行
- §7 部署：描述三个 Dockerfile + compose 三容器 + GPU 资源要求
- §10 风险点：
  - 删 "router ML 依赖体积"（已解决）
  - 加 "GPU Pool 单副本 SPOF"（决策 6 的代价）
  - 加 "router-service ↔ GPU Pool 网络抖动影响路由延迟"
- §11 快速索引：
  - "改路由阈值/权重" → `runtime_config.json`（router-service）
  - "换 ML 模型" → `model_paths.json`（GPU Pool）+ 重启 gpu-pool 容器
  - "部署 GPU Pool" → `docker compose build gpu-pool`

### T18 · 完整 harness run

```bash
# L0+L1
uv run ruff check .
uv run pytest                      # 基线不降
uv run check-env gpu-pool          # 新增服务能通过校验

# L2 部署
docker compose build
docker compose up -d

# 三容器健康
curl http://localhost:8001/ready   # backend-app
curl http://localhost:8003/ready   # router-service
curl http://localhost:8014/ready   # gpu-pool

# 端到端
curl -X POST http://localhost:8003/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -d '{"model":"auto","messages":[{"role":"user","content":"写个 python hello world"}]}'
# 期望：看到 gpu-pool 的 routing.jsonl 和 router-service 的 upstream.jsonl 都有对应 request_id 记录
```

所有输出贴 PR 描述。

---

## 非目标（本次不做）

- **GPU Pool 多副本 LB**：决策 6 暂按单台 GPU 规划；未来扩容时另起规划评估 Nginx / K8s Service / 内置轮询客户端
- **GPU Pool 代理上游 LLM**：Pool 只做 ML 推理，不做 upstream completion 转发（职责单一）
- **改内部 HMAC loopback → 进程内直呼**：backend-app 内部 6 条 HMAC over loopback 保留（可回滚价值）
- **拆 `.env` 为三份**：变更面太大，等三镜像稳定后另做
- **不删除 `src/admin_service/main.py` 等单域入口**：保留调试价值
- **不重启用 skip 测试**
- **不调整 `migrations/` 结构**
- **router-service 是否允许 import `common.*`**：T14 中暂不引入依赖，保持 router 零 common 依赖现状；若 GPU Pool client 的异常处理复杂化需要引入，再单独评估

---

## 关键文件索引

| 职责 | 文件 |
|---|---|
| 环境校验 | `scripts/check_service_environment.py`（T2）|
| 启动脚本 | `scripts/start_services.py`（T15 后同步加 gpu-pool）|
| 健康探针 | `scripts/runtime_probe.py`（gpu-pool 复用 http-ready）|
| SQL 快照 | `scripts/sql/*.sql`（T3 删 router_schema） |
| 容器构建 | `deploy/Dockerfile.control-plane` / `Dockerfile.router` / `Dockerfile.gpu-pool`（T13 新建）|
| 容器编排 | `deploy/docker-compose.yml`（T15） |
| 控制面入口 | `src/backend_app/main.py` |
| 数据面（CPU）入口 | `src/router_service/main.py`（T14 改造）|
| 数据面（GPU）入口 | `src/gpu_pool/main.py`（T11 新建）|
| ML 核心 | `src/gpu_pool/services/inference.py`（T12 搬迁）|
| 路由映射配置 | `deploy/router/runtime_config.json`（router-service 独占）|
| ML 模型路径配置 | `deploy/router/model_paths.json`（GPU Pool 独占；后续可迁 `deploy/gpu_pool/`）|
| 旧内部路由 | `src/testing_service/api/v1/endpoints/internal_router.py`（T4 删除）|
| 跨服务客户端 | `src/*/services/*_client.py`（原 5 条）+ `src/router_service/services/gpu_pool_client.py`（T14 新增，第 6 条）|
| 架构文档 | `docs/ARCHITECTURE.md`（T17） |
| 守护测试 | `tests/test_backend_app.py`、`test_schema_ownership.py`、`test_service_environment.py`、`test_runtime_orchestration.py`、`test_internal_contracts.py`、`test_gpu_pool_contract.py`（T16 新建）、`test_router_calls_pool.py`（T16 新建）|

---

## 验证摘要（端到端）

迁移完成后，以下断言**都为真**：

1. `grep -R "ROUTER_DATABASE_URL" .` 仅在文档注释里出现或完全不出现
2. `ls scripts/sql/router_schema.sql` 不存在
3. `grep -R "internal/router" src/` 0 条
4. `grep -R "HybridIntegratedDifficultyRouter" src/router_service/` 0 条（已搬走）
5. `grep -R "HybridIntegratedDifficultyRouter" src/gpu_pool/` 有命中
6. `docker image` 大小：control-plane ~500MB-1GB；router-service <500MB；gpu-pool ~3-5GB
7. `docker compose build router-service` 日志**不含** `torch`；`docker compose build gpu-pool` 日志**含** `torch`
8. `uv run pytest`：基线 168 passed / 7 skipped，加上 T16 新增用例后数量上升（允许），skipped 不增
9. 三容器起起来，`/ready` 全 200
10. 一次 `POST /v1/chat/completions` 请求能看到 `gpu-pool routing.jsonl` + `router-service routing.jsonl` + `router-service upstream.jsonl` 三条记录同 `request_id`

---

## Appendix · GPU Pool 接口 v1 契约

**端点**：`POST /classify` (GPU Pool, 默认 :8014)

**Headers**：
- `X-Pool-Auth: <GPU_POOL_SECRET>`（必需）
- `X-Request-ID: <req-abc>`（可选，透传）

**Request Body**：
```json
{
  "request_id": "req-abc",
  "messages": [{"role": "user", "content": "..."}],
  "requested_model": "auto"
}
```

**Response Body（200）**：
```json
{
  "request_id": "req-abc",
  "scores_0_2": {"纠错": 0.92, "工具调用": 1.43, "通用任务": 0.78, "任务拆解": 1.12, "编程": 0.65},
  "proto_weighted_0_2": 1.21,
  "total_score_0_10": 6.05,
  "score_source": "proto_weighted_0_2",
  "latency_ms": 42.1,
  "backbone_version": "qwen-0.5b-router-v1"
}
```

**错误码**：
- 401：缺 `X-Pool-Auth`
- 403：`X-Pool-Auth` 不匹配
- 422：request body 不合法
- 500：ML 推理异常（router-service 应降级或返回 503）
- 503：模型未加载完成（启动期）

**契约变更规则**：改 request/response 字段必须升 `/v2/classify`，v1 保留一个版本周期。
