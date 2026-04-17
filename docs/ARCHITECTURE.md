# Eucal AI Backend — 项目架构文档

> 更新：2026-04-17（双轨重构后）
> 范围：`F:\Eucal_AI\backend`

---

## 1. 总体架构

Eucal AI 后端采用 **Control Plane / Data Plane** 拆分，降低运维复杂度的同时保留 router 的水平扩容能力：

- **backend-app**（:8001）—— 单个 FastAPI 进程承载 admin + user + content + testing 四个管理面域。所有非性能关键的 CRUD、鉴权、目录管理都在这里。
- **router-service**（:8003）—— 独立进程，OpenAI 兼容代理的热路径，需要时可水平扩容成 N 副本。
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
          │  /api/v1/admin/auth/*   │  │  OpenAI 兼容         │
          │  /api/v1/admin-users/*  │  │  router key/计费     │
          │  /api/v1/invitation-*   │  │                     │
          │  /api/v1/news/*         │  │                     │
          │  /api/v1/models/*       │  │                     │
          │  /api/v1/providers/*    │  │                     │
          │  /api/v1/benchmark/*    │  │                     │
          │  /api/v1/internal/*     │◄─┤ HMAC 调用            │
          │                         │  │ (users / router)    │
          └────┬────────────────────┘  └─────────────────────┘
               │
               ├─ testing-scheduler :8012
               └─ testing-worker    (arq + Redis)
```

### 核心设计原则

- **Control Plane / Data Plane 拆分**：非热路径全部合一（backend-app），热路径独立（router-service）
- **Database-per-service**：5 个 MySQL 库依然独立（admin/user/content/router/testing），backend-app 内部持 4 个 engine
- **异步优先**：FastAPI + SQLAlchemy 2 async + aiomysql + httpx
- **Snowflake ID**：全局唯一 ID（`common/utils/snowflake.py`，`SnowflakeIdMixin`）
- **签名调用**：跨进程 HTTP 调用走 HMAC（`common/internal.py`）；backend-app 内部调用仍走 localhost HMAC（loopback 成本 <5ms），为回滚保留兼容
- **统一配置**：`.env` 由 pydantic-settings 加载，backend-app 组合 4 个子服务 Settings

---

## 2. 服务与进程清单

| 进程 | 模块 | 端口 | 数据库 | 扩容 |
|---|---|---|---|---|
| **backend-app** | `backend_app` | 8001 | admin/user/content/testing 4 库 | 单实例（可做多实例无状态） |
| **router-service** | `router_service` | 8003 | `eucal_ai_router` | 水平扩容 |
| **testing-scheduler** | `testing_service.main:app` | 8012 | `eucal_ai_testing` | 单实例 |
| **testing-worker** | `testing_service.worker` | — | `eucal_ai_testing` | 按队列深度扩容 |

子服务的 `*_service/main.py` 仍保留，用于 **单域调试**（`uv run start admin-service` 会起 admin 独立进程）。默认 `uv run start` 只启动上表 4 个进程。

### 2.1 backend-app 内部子域

每个子域依旧是独立的 Python 包：

| 域 | 包 | ORM 模型 | FastAPI 端点 |
|---|---|---|---|
| admin | `admin_service` | `admin_users`, `invitation_codes`, `admin_audit_logs` | `/api/v1/admin/auth/*`, `/api/v1/admin-users/*`, `/api/v1/admin-audit-logs/*`, `/api/v1/invitation-codes/*`, `/api/v1/dashboard/*` |
| user | `user_service` | `users`, `user_sessions`, `user_active_sessions`, `email_verification_codes` | `/api/v1/auth/*` |
| content | `content_service` | `news` | `/api/v1/news/*`, `/api/v1/admin/news/*` |
| testing | `testing_service` | `models`, `providers`, `model_provider_offerings`, `benchmark_jobs`, 等 | `/api/v1/models/*`, `/api/v1/providers/*`, `/api/v1/vendors/*`, `/api/v1/benchmark/*`, `/api/v1/model-providers/*` |
| internal | 各子域的 `internal.py` | — | `/api/v1/internal/admins/*`, `/api/v1/internal/invitation-codes/*`, `/api/v1/internal/users/*`, `/api/v1/internal/router/*` |

### 2.2 路径冲突处理

两处路径冲突已在 backend-app 层解决：

| 冲突 | 解决 |
|---|---|
| `/api/v1/auth/*` admin vs user | admin 公共路由挂到 `/api/v1/admin/*`；user 保持 `/api/v1/auth/*` 面向终端用户 |
| `/api/v1/news` user 代理 vs content | backend-app 不注册 user 的 news 代理路由；content 直接服务 |

admin 的**内部 HMAC 端点**（`/api/v1/internal/admins/*`、`/api/v1/internal/invitation-codes/*`）保持原路径不变，避免打断 HMAC 客户端。

---

## 3. 耦合矩阵（重构后）

### 3.1 进程间 HMAC 调用

| Caller ↓ / Callee → | backend-app | router-service |
|---|---|---|
| **router-service** | `fetch_user_by_uid`、`fetch_user_by_id`（走 user 内部端点）；`list_models`、`resolve_routes`、`get_offering`（走 testing 内部端点） | — |
| **testing-worker** | `fetch_admin_by_uid`（走 admin 内部端点） | — |

**只剩 2 方向**：router → backend-app；testing-worker → backend-app。其他所有历史 HMAC 调用都变成 backend-app 内部的 loopback。

### 3.2 backend-app 内部 loopback 调用（仍走 HMAC over localhost）

| Caller ↓ / Callee → | admin | user | content | testing |
|---|---|---|---|---|
| admin | — | `fetch_total_users` | — | — |
| user | `consume_invitation_code`、`release_invitation_code` | — | `list_news`、`get_news` | — |
| content | `fetch_admin_by_uid` | — | — | — |
| testing | `fetch_admin_by_uid` | — | — | — |

**为什么保留 HMAC**：一行代码没改，可以随时分拆回 5 个独立服务（回滚 <5 分钟）。上线稳定后若想优化，可改为进程内直呼（优化 <5ms 延迟）。

---

## 4. 共享层（`common/`）

| 子模块 | 职责 |
|---|---|
| `config.py` | `BaseServiceSettings`（JWT/INTERNAL_SECRET/CORS/DB 池） |
| `db/` | `ServiceDatabaseRuntime`（async engine + session）、`SnowflakeIdMixin`、`TimestampMixin` |
| `internal.py` | HMAC 签名、断路器、跨服务错误映射 |
| `core/` | 全局异常处理 |
| `health.py` | `/health`、`/ready` 响应构造 |
| `observability.py` | 结构化日志、请求 ID |
| `utils/` | jwt / crypto / password / snowflake / timezone / openai_compat |

backend-app 在 lifespan 里**单次**调用 `configure_snowflake`、`install_observability`、`register_exception_handlers`、`add_middleware(CORSMiddleware)`；各子域无需重复注册。

---

## 5. 数据库与 Alembic

**5 个独立 MySQL 库**：`eucal_ai_{admin, user, content, router, testing}`。不跨库外键；跨域引用（`router_usage_events.owner_user_id` → user.users.id）靠应用层。

**统一 Alembic 环境**：

```
migrations/
├── _env_shared.py          唯一的 Alembic env 逻辑
├── helpers.py              revision 可复用工具
├── cutover_manifest.json   phase2-cutover 所有权图（活文档）
├── README.md               真理来源说明 + 工作流
├── admin_service/
│   ├── env.py              3-line 代理
│   ├── script.py.mako
│   └── versions/
├── user_service/           ... (结构同 admin)
├── content_service/
├── router_service/
└── testing_service/
```

每个服务的 `env.py` 是 3 行代理到 `_env_shared.run_env()`；服务身份通过 Alembic 主选项注入（`service_name`、`service_package`、`database_env`）。

**命令**：
```bash
uv run migrate --service <name> upgrade head
uv run migrate --service <name> revision -m "..." --autogenerate
uv run bootstrap-databases                  # 5 库一把 upgrade
```

`scripts/sql/*.sql` 是 `phase2-cutover` 工具引用的 schema 快照，**不是真理**。详见 `migrations/README.md`。

---

## 6. 运行脚本

| 命令 | 用途 |
|---|---|
| `uv run start` | 默认启动 backend-app + router-service + testing-worker + testing-scheduler |
| `uv run start admin-service user-service` | 单域启动（调试） |
| `uv run check-env` | 环境变量完整性校验（含 backend-app 的 4 个 DB URL） |
| `uv run migrate --service <x> upgrade head` | 单服务 Alembic 操作 |
| `uv run bootstrap-databases` | 所有服务 upgrade head |
| `uv run bootstrap-super-admin` | 初始化超级管理员 |
| `uv run phase2-cutover` | 历史 phase2 切换工具 |

---

## 7. 部署

`deploy/docker-compose.yml`：

| 容器 | 镜像 | 端口 | 依赖 |
|---|---|---|---|
| **backend-app** | 自构建 | 8001 | mysql (外部) |
| **router-service** | 自构建 | 8003 | backend-app |
| **redis** | redis:7-alpine | — | — |
| **testing-worker** | 自构建 | — | backend-app, redis |
| **testing-scheduler** | 自构建（profile=scheduler） | 8012 | backend-app, redis |

**运行时依赖**：MySQL 8.x（5 个库）、Redis 7.x（arq 队列）。

---

## 8. 测试布局（`tests/`）

| 分类 | 文件 |
|---|---|
| backend-app 聚合 | `test_backend_app.py`（路由唯一性、内部端点可达、健康检查） |
| 迁移结构 | `test_migration_structure.py`（统一 env、独立 revision 链、CLI） |
| 服务功能 | `test_admin.py`、`test_admin_management.py`、`test_user.py`、`test_router.py`、`test_testing.py`、`test_common.py` |
| 架构一致性 | `test_architecture_boundaries.py`、`test_schema_drift.py`、`test_schema_ownership.py` |
| 跨服务契约 | `test_internal_contracts.py` |
| 运行时编排 | `test_runtime_orchestration.py`、`test_runtime_probe.py`、`test_service_environment.py` |
| 队列与基准 | `test_benchmark_queue.py`、`test_testing_api.py` |

`pytest`：`asyncio_mode = "auto"`、`testpaths = ["tests"]`。

---

## 9. 未来 DB 可移植性铺垫

为将来迁移 PostgreSQL 做的零成本标注（不影响 MySQL 运行）：

- `User.email` 列 comment 明示 "store lowercase + trimmed at write"，迁移 Postgres 时避免大小写敏感踩坑
- `Model.capability_tags` 列 comment 明示 "migrate to JSONB for GIN indexing"
- `migrations/README.md` 记录 DateTime 约定：**UTC naive 存储，应用层负责时区转换**；未来 Postgres 升级 `TIMESTAMPTZ` 时重审

**当前不做**：DB 引擎切换、ORM 搬到 common/ 共享。等上线 6+ 个月后根据真实负载再评估。

---

## 10. 关键耦合风险点

1. **HMAC 断路器是进程内状态**（`common/internal.py::_CIRCUIT_BREAKERS`）。router-service 多副本时各副本独立；backend-app 单副本时影响对称
2. **跨服务事务无保障**：邀请码 consume/release 是两次 HMAC 调用；register 失败由 user-side 主动 release
3. **backend-app 单点**：若宕机，所有管理面不可用；router-service 大部分请求（JWT 本地验证）不受影响，只有 user-status-check 会调 backend。上线后可按需开 backend-app 多副本
4. **路由冲突靠 pytest gate**：`tests/test_backend_app.py::test_route_uniqueness` 是合并门禁；新增路由若撞其他域会在 CI 失败
5. **共享 .env**：env 变量前缀必须严格遵守；`check-env` 校验所有必需变量
6. **SmartRouter 旁路 testing-service**：`router_service.services.smart_router_service` 直接用 litellm 做难度分类，依赖 `SMART_ROUTER_CLASSIFIER_MODEL` 配置一致

---

## 11. 快速索引

| 你想... | 看这里 |
|---|---|
| 添加一个新的端点 | 在对应 `<service>/api/v1/endpoints/` 新建模块；更新 `<service>/api/v1/router.py`；backend-app 自动挂载（因为 include 的是 `api_router`） |
| 添加一个跨进程调用 | 在 caller `services/<target>_client.py` 新增；在 target 的 `internal.py` 暴露端点；更新 caller `config.py` 的 URL 变量（多数情况指向 `backend-app:8001`） |
| 改数据库 schema | `uv run migrate --service <name> revision -m "..." --autogenerate`，审查生成的 revision |
| 理解 backend-app 路由组织 | `backend_app/main.py` 里 `_build_admin_public_api_router` / `_build_admin_internal_api_router` / `_build_user_api_router_without_news` |
| 回滚合并 | `scripts/start_services.py::DEFAULT_SERVICES` 改回原 5 服务列表，`docker-compose.yml` 改回每服务一个容器 |
| 查看哪些路径是 backend-app 的 | `uv run pytest tests/test_backend_app.py -v` 会打印所有注册路径并校验唯一 |
