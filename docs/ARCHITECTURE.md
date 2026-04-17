# Eucal AI Backend — 项目架构文档

> 更新：2026-04-17（src/ layout 规范化 + 旧 router 功能下线）
> 范围：`F:\Eucal_AI\backend`

---

## 1. 总体架构

Eucal AI 后端采用 **Control Plane / Data Plane** 拆分，配合 src/ layout 统一代码布局：

- **backend-app**（:8001）—— 单个 FastAPI 进程承载 admin + user + content + testing 四个管理面域。所有 CRUD、鉴权、目录管理都在这里。
- **router-service**（:8003）—— 独立进程，**纯 ML 推理路由**（Hybrid Integrated Difficulty Router）。无数据库、无 HMAC、无 API Key/计费。水平扩容友好。
- **testing-scheduler**（:8012）+ **testing-worker**（arq）—— 独立后台进程，跑 apscheduler 和基准测试队列消费者。

```
┌────────────────────────────────────────────────────────┐
│                 客户端 / 前端 / LLM 调用方                 │
└──────────────────────┬──────────────────┬──────────────┘
                       │                  │
          ┌────────────▼────────────┐  ┌──▼──────────────────┐
          │       backend-app       │  │   router-service    │
          │         :8001           │  │       :8003         │
          │                         │  │  (可扩容 N 副本)     │
          │  /api/v1/auth/*         │  │                     │
          │  /api/v1/admin/auth/*   │  │  /v1/chat/*         │
          │  /api/v1/admin-users/*  │  │  /v1/completions/*  │
          │  /api/v1/invitation-*   │  │  /v1/models         │
          │  /api/v1/news/*         │  │  /v1/router/config  │
          │  /api/v1/models/*       │  │  /ready             │
          │  /api/v1/providers/*    │  │                     │
          │  /api/v1/benchmark/*    │  │  ML 推理，无 DB      │
          │  /api/v1/internal/*     │  │  无 HMAC callout    │
          │                         │  │                     │
          └────┬────────────────────┘  └─────────────────────┘
               │
               ├─ testing-scheduler :8012
               └─ testing-worker    (arq + Redis)
```

### 核心设计原则

- **Control Plane / Data Plane 拆分**：非热路径全部合一（backend-app），热路径独立（router-service）
- **src/ layout**：所有 Python 包位于 `src/` 下（`src/common`、`src/admin_service`、…、`src/backend_app`），pyproject hatchling 统一打包
- **Database-per-service**：4 个 MySQL 库独立（admin/user/content/testing），backend-app 内部持 4 个 engine；router 无 DB
- **异步优先**：FastAPI + SQLAlchemy 2 async + aiomysql + httpx
- **Snowflake ID**：全局唯一 ID（`common/utils/snowflake.py`，`SnowflakeIdMixin`）
- **签名调用**：跨进程 HTTP 调用走 HMAC（`common/internal.py`）；backend-app 内部调用仍走 localhost HMAC（loopback 成本 <5ms），为回滚保留兼容。router 不参与 HMAC
- **ML 依赖分层**：numpy/torch/transformers 等进 `[project.optional-dependencies].router`，默认 `uv sync` 不装，避免把 1GB+ 依赖强加给所有开发者

---

## 2. 服务与进程清单

| 进程 | 模块 | 端口 | 数据库 | 依赖 | 扩容 |
|---|---|---|---|---|---|
| **backend-app** | `backend_app.main:app` | 8001 | admin/user/content/testing 4 库 | 标准依赖 | 单实例（可做多实例无状态） |
| **router-service** | `router_service.main:app` | 8003 | — | `uv sync --extra router`（含 torch） | 水平扩容 |
| **testing-scheduler** | `testing_service.main:app` | 8012 | `eucal_ai_testing` | 标准依赖 | 单实例 |
| **testing-worker** | `testing_service.worker.WorkerSettings`（arq） | — | `eucal_ai_testing` | 标准依赖 | 按队列深度扩容 |

子服务的 `src/<service>/main.py` 仍保留，用于 **单域调试**（`uv run start admin-service` 会起 admin 独立进程）。默认 `uv run start` 启动上表 4 个进程。

### 2.1 backend-app 内部子域

每个子域依旧是独立的 Python 包，全部位于 `src/`：

| 域 | 包 | ORM 模型 | FastAPI 端点 |
|---|---|---|---|
| admin | `src/admin_service` | `admin_users`, `invitation_codes`, `admin_audit_logs` | `/api/v1/admin/auth/*`, `/api/v1/admin-users/*`, `/api/v1/admin-audit-logs/*`, `/api/v1/invitation-codes/*`, `/api/v1/dashboard/*` |
| user | `src/user_service` | `users`, `user_sessions`, `user_active_sessions`, `email_verification_codes` | `/api/v1/auth/*` |
| content | `src/content_service` | `news` | `/api/v1/news/*`, `/api/v1/admin/news/*` |
| testing | `src/testing_service` | `models`, `providers`, `model_provider_offerings`, `benchmark_jobs`, 等 | `/api/v1/models/*`, `/api/v1/providers/*`, `/api/v1/vendors/*`, `/api/v1/benchmark/*`, `/api/v1/model-providers/*` |
| internal | 各子域的 `internal.py` | — | `/api/v1/internal/admins/*`, `/api/v1/internal/invitation-codes/*`, `/api/v1/internal/users/*` |

### 2.2 路径冲突处理

两处路径冲突已在 backend-app 层解决：

| 冲突 | 解决 |
|---|---|
| `/api/v1/auth/*` admin vs user | admin 公共路由挂到 `/api/v1/admin/*`；user 保持 `/api/v1/auth/*` 面向终端用户 |
| `/api/v1/news` user 代理 vs content | backend-app 不注册 user 的 news 代理路由；content 直接服务 |

admin 的**内部 HMAC 端点**（`/api/v1/internal/admins/*`、`/api/v1/internal/invitation-codes/*`）保持原路径不变，避免打断 HMAC 客户端。

### 2.3 router-service 独立性

新 router 是 ML 推理服务，与其他服务**没有共享**：

- 不用 `BaseServiceSettings`；配置靠 `runtime_config.json` + `model_paths.json`（位于 `deploy/router/`，可用 `ROUTER_RUNTIME_CONFIG`/`ROUTER_MODEL_PATHS` 环境变量覆盖）
- 不用 `ServiceDatabaseRuntime`；没有 ORM
- 不用 `common.internal`；不主动调用其他服务
- 自带 `router_service/logging.py`（不走 `common.observability`）；未来可按需统一

---

## 3. 进程间调用

### 3.1 HMAC 调用（重构后）

| Caller ↓ / Callee → | backend-app |
|---|---|
| **testing-worker** | `fetch_admin_by_uid`（走 admin 内部端点） |

**只剩 1 个方向**：testing-worker → backend-app（审计用 actor 身份解析）。其他所有历史 HMAC 调用要么变成 backend-app 内部的 loopback，要么已随旧 router 功能一并下线。

### 3.2 backend-app 内部 loopback 调用（仍走 HMAC over localhost）

| Caller ↓ / Callee → | admin | user | content | testing |
|---|---|---|---|---|
| admin | — | `fetch_total_users` | — | — |
| user | `consume_invitation_code`、`release_invitation_code` | — | `list_news`、`get_news` | — |
| content | `fetch_admin_by_uid` | — | — | — |
| testing | `fetch_admin_by_uid` | — | — | — |

**为什么保留 HMAC**：一行代码没改，可以随时分拆回 4 个独立服务（回滚 <5 分钟）。上线稳定后若想优化，可改为进程内直呼（省 <5ms 延迟）。

### 3.3 router ↔ 外部

router 当前不主动调用 backend-app；调用方直接打 `:8003/v1/chat/completions` 等端点，router 本地完成路由决策后向上游 LLM 发起 completion。上游地址由 `runtime_config.json` 管理。

---

## 4. 共享层（`src/common/`）

| 子模块 | 职责 |
|---|---|
| `config.py` | `BaseServiceSettings`（JWT/INTERNAL_SECRET/CORS/DB 池） |
| `db/` | `ServiceDatabaseRuntime`（async engine + session）、`SnowflakeIdMixin`、`TimestampMixin` |
| `internal.py` | HMAC 签名、断路器、跨服务错误映射 |
| `core/` | 全局异常处理 |
| `health.py` | `/health`、`/ready` 响应构造 |
| `observability.py` | 结构化日志、请求 ID |
| `utils/` | jwt / crypto / password / snowflake / timezone / openai_compat |

backend-app 在 lifespan 里**单次**调用 `configure_snowflake`、`install_observability`、`register_exception_handlers`、`add_middleware(CORSMiddleware)`；各子域无需重复注册。router-service 不接入 common 层（见 §2.3）。

---

## 5. 数据库与 Alembic

**4 个独立 MySQL 库**：`eucal_ai_{admin, user, content, testing}`。router 无 DB。不跨库外键；跨域引用（如 audit log 里的 actor user_id）靠应用层。

**统一 Alembic 环境**：

```
migrations/
├── _env_shared.py          唯一的 Alembic env 逻辑
├── helpers.py              revision 可复用工具
├── cutover_manifest.json   phase2-cutover 历史产物（含旧 router 条目，已归档）
├── README.md               真理来源说明 + 工作流
├── admin_service/
│   ├── env.py              3-line 代理
│   ├── script.py.mako
│   └── versions/
├── user_service/           ... (结构同 admin)
├── content_service/
└── testing_service/
```

每个服务的 `env.py` 是 3 行代理到 `_env_shared.run_env()`；服务身份通过 Alembic 主选项注入（`service_name`、`service_package`、`database_env`）。`scripts/migrate.py` 在调用时把 `backend/` 与 `backend/src/` 都加入 Alembic 的 `prepend_sys_path`，确保 `from migrations._env_shared` 与 `from <service> import ...` 都能解析。

**命令**：
```bash
uv run migrate --service <name> upgrade head
uv run migrate --service <name> revision -m "..." --autogenerate
uv run bootstrap-databases                  # 4 库一把 upgrade
```

`scripts/sql/*.sql` 是 `phase2-cutover` 工具引用的 schema 快照，**不是真理**。详见 `migrations/README.md`。

---

## 6. 运行脚本

`scripts/` 是横切 CLI 工具层（`scripts/__init__.py` 使之成为正式包，entry point 能 import）。

| 命令 | 用途 |
|---|---|
| `uv run start` | 默认启动 backend-app + router-service + testing-worker + testing-scheduler |
| `uv run start admin-service user-service` | 单域启动（调试） |
| `uv run check-env` | 环境变量完整性校验（含 backend-app 的 4 个 DB URL） |
| `uv run migrate --service <x> upgrade head` | 单服务 Alembic 操作 |
| `uv run bootstrap-databases` | 4 个服务 upgrade head |
| `uv run bootstrap-super-admin` | 初始化超级管理员 |
| `uv run phase2-cutover` | 历史 phase2 切换工具（旧 router 下线后主要为归档参考） |
| `python scripts/runtime_probe.py http-ready --port <n>` | 容器 healthcheck（由 compose 直接调用） |

---

## 7. 部署

`deploy/docker-compose.yml`：

| 容器 | 镜像 | 端口 | 依赖 |
|---|---|---|---|
| **backend-app** | 自构建 | 8001 | mysql (外部) |
| **router-service** | 自构建 | 8003 | — |
| **redis** | redis:7-alpine | — | — |
| **testing-worker** | 自构建 | — | backend-app, redis |
| **testing-scheduler** | 自构建（profile=scheduler） | 8012 | backend-app, redis |

**运行时依赖**：MySQL 8.x（4 个库）、Redis 7.x（arq 队列）。

**镜像布局**：`Dockerfile` `COPY src/* /app/src/`，`PYTHONPATH=/app/src` 让 `import admin_service` 等仍为裸名。router 运行时资产 `deploy/router/{runtime_config,model_paths}.json` 也 COPY 进镜像，容器里路径 `/app/deploy/router/`。

---

## 8. 测试布局（`tests/`）

| 分类 | 文件 |
|---|---|
| backend-app 聚合 | `test_backend_app.py`（路由唯一性、内部端点可达、健康检查） |
| 迁移结构 | `test_migration_structure.py`（统一 env、独立 revision 链、CLI） |
| 服务功能 | `test_admin.py`、`test_admin_management.py`、`test_user.py`、`test_testing.py`、`test_testing_api.py`、`test_common.py` |
| 架构一致性 | `test_schema_drift.py`、`test_schema_ownership.py` |
| 跨服务契约 | `test_internal_contracts.py` |
| 运行时编排 | `test_runtime_orchestration.py`、`test_runtime_probe.py`、`test_service_environment.py`、`test_phase4_runtime.py` |
| 队列与基准 | `test_benchmark_queue.py` |

`pytest`：`asyncio_mode = "auto"`、`testpaths = ["tests"]`。全量跑 `uv run pytest`：当前 **168 passed, 7 skipped**。

### 8.1 暂停的测试

以下测试模块级 `pytest.skip` 或直接删除，原因是断言旧 router 的 key/billing/openai-compat/identity 子系统（已下线）：

| 文件 | 状态 | 说明 |
|---|---|---|
| `test_router.py` | 已删除 | 专测旧 router |
| `test_phase2_cutover.py` | 全文件 skip | manifest 绑死旧 router |
| `test_phase4_acceptance.py` | 全文件 skip | openai-compat/keys/billing 端到端 |
| `test_phase4_degradation.py` | 全文件 skip | `router_service.dependencies.get_current_user` 等 |
| `test_review_fixes.py` | 全文件 skip | 硬编码路径 + 旧 router 架构断言 |
| `test_architecture_boundaries.py` | 全文件 skip | 架构不变量绑旧 router |
| `test_internal_contracts.py` | 2 个用例 skip | router.identity_client / testing_catalog_client |

重新引入条件：旧 key/billing 功能在新 router（或拆出独立服务）落地后，重写对应测试。

---

## 9. 未来 DB 可移植性铺垫

为将来迁移 PostgreSQL 做的零成本标注（不影响 MySQL 运行）：

- `User.email` 列 comment 明示 "store lowercase + trimmed at write"，迁移 Postgres 时避免大小写敏感踩坑
- `Model.capability_tags` 列 comment 明示 "migrate to JSONB for GIN indexing"
- `migrations/README.md` 记录 DateTime 约定：**UTC naive 存储，应用层负责时区转换**；未来 Postgres 升级 `TIMESTAMPTZ` 时重审

**当前不做**：DB 引擎切换、ORM 搬到 common/ 共享。等上线 6+ 个月后根据真实负载再评估。

---

## 10. 关键耦合风险点

1. **HMAC 断路器是进程内状态**（`common/internal.py::_CIRCUIT_BREAKERS`）。backend-app 多副本时各副本独立；单副本时影响对称
2. **跨服务事务无保障**：邀请码 consume/release 是两次 HMAC 调用；register 失败由 user-side 主动 release
3. **backend-app 单点**：若宕机，所有管理面不可用；router-service 完全独立（不依赖 backend-app），对推理流无影响。上线后可按需开 backend-app 多副本
4. **路由冲突靠 pytest gate**：`tests/test_backend_app.py::test_route_uniqueness` 是合并门禁；新增路由若撞其他域会在 CI 失败
5. **共享 .env**：env 变量前缀必须严格遵守；`check-env` 校验所有必需变量
6. **router ML 依赖体积**：torch + transformers ≈ 1–2 GB；默认 `uv sync` 不装，必须 `--extra router`。CI/部署流水线需显式启用该 extra
7. **router 配置文件**：`deploy/router/runtime_config.json`、`model_paths.json` 是 router 启动必需；缺失时 `create_app()` 在 lifespan 阶段会失败。容器镜像在 `deploy/Dockerfile` 里显式 COPY 到 `/app/deploy/router/`
8. **旧功能下线面**：router key/billing/identity/openai-compat 全部暂时缺失。若前端或上游客户端仍在打 `/v1/chat/completions` 并假设鉴权存在，需同步适配

---

## 11. 快速索引

| 你想... | 看这里 |
|---|---|
| 添加一个新的端点 | 在对应 `src/<service>/api/v1/endpoints/` 新建模块；更新 `src/<service>/api/v1/router.py`；backend-app 自动挂载（因为 include 的是 `api_router`） |
| 添加一个跨进程调用 | 在 caller `src/<service>/services/<target>_client.py` 新增；在 target 的 `internal.py` 暴露端点；更新 caller `config.py` 的 URL 变量（多数情况指向 `backend-app:8001`） |
| 改数据库 schema | `uv run migrate --service <name> revision -m "..." --autogenerate`，审查生成的 revision |
| 理解 backend-app 路由组织 | `src/backend_app/main.py` 里 `_build_admin_public_api_router` / `_build_admin_internal_api_router` / `_build_user_api_router_without_news` |
| 改 router 路由权重 | `deploy/router/runtime_config.json`，或通过 `/v1/router/config` 查看当前配置 |
| 装 router ML 依赖 | `uv sync --extra router` |
| 回滚合并 | `scripts/start_services.py::DEFAULT_SERVICES` 改回原 4 服务列表（admin/user/content/testing 单独起），`docker-compose.yml` 改回每服务一个容器 |
| 回滚到重构前 | `git reset --hard backup/pre-restructure`（tag 保留在 commit `3057e18`） |
| 查看哪些路径是 backend-app 的 | `uv run pytest tests/test_backend_app.py -v` 会打印所有注册路径并校验唯一 |
