# 后端项目目录结构总览

> 更新时间：2026-04-20  
> 范围：当前工作区 `/home/luofei/backend`  
> 说明：本清单覆盖仓库内当前可见的项目目录与文件；`.git/` 未展开；`.venv/`、`__pycache__/`、`.ruff_cache/` 这类第三方或运行缓存目录会说明用途，但不会逐个展开所有自动生成文件。

## 1. 根目录与本地配置

- `./`：后端仓库根目录。
- `.claude/`：Claude/Codex 本地协作配置目录。
- `.claude/settings.local.json`：本地 AI 协作工具设置。
- `.codex/`：Codex 本地工作目录，当前为空。
- `.dockerignore`：Docker 构建忽略规则。
- `.env`：当前本地运行环境变量文件。
- `.env.example`：环境变量模板文件。
- `.gitignore`：Git 忽略规则。
- `.idea/`：JetBrains IDE 项目配置目录。
- `.idea/.gitignore`：IDE 目录自身的忽略配置。
- `.idea/backend.iml`：IDE 模块定义文件。
- `.idea/dataSources/`：IDE 数据源缓存目录。
- `.idea/dataSources.local.xml`：本地数据源配置。
- `.idea/dataSources.xml`：IDE 数据源定义。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/`：某个数据库连接的数据缓存目录。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8.xml`：该数据源的详细配置。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/`：IDE 数据源存储目录。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/`：数据源源码缓存子目录。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/`：数据库 schema 快照目录。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/eucal.HvXFBQ.meta`：`eucal` 库的元数据缓存。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/eucal.HvXFBQ.zip`：`eucal` 库结构压缩快照。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/eucal_testing.78_Mhg.meta`：`eucal_testing` 库元数据缓存。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/eucal_testing.78_Mhg.zip`：`eucal_testing` 库结构压缩快照。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/information_schema.FNRwLQ.meta`：MySQL `information_schema` 元数据缓存。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/mysql.osA4Bg.meta`：MySQL 系统库元数据缓存。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/performance_schema.kIw0nw.meta`：性能库元数据缓存。
- `.idea/dataSources/94e1e78b-1fe5-403e-a841-62a1ec00ede8/storage_v2/_src_/schema/sys.zb4BAA.meta`：`sys` 库元数据缓存。
- `.idea/data_source_mapping.xml`：IDE 数据源映射关系。
- `.idea/inspectionProfiles/`：IDE 检查规则目录。
- `.idea/inspectionProfiles/Project_Default.xml`：项目默认检查规则。
- `.idea/inspectionProfiles/profiles_settings.xml`：检查规则配置。
- `.idea/misc.xml`：IDE 杂项项目设置。
- `.idea/modules.xml`：IDE 模块索引。
- `.idea/sqldialects.xml`：SQL 方言配置。
- `.idea/vcs.xml`：版本控制集成配置。
- `.idea/workspace.xml`：IDE 本地工作区状态。
- `.pytest_cache/`：pytest 运行缓存目录。
- `.pytest_cache/.gitignore`：pytest 缓存目录忽略文件。
- `.pytest_cache/CACHEDIR.TAG`：缓存目录标识。
- `.pytest_cache/README.md`：pytest 缓存说明。
- `.pytest_cache/v/`：pytest 缓存版本目录。
- `.pytest_cache/v/cache/`：pytest 核心缓存目录。
- `.pytest_cache/v/cache/lastfailed`：最近失败用例缓存。
- `.pytest_cache/v/cache/nodeids`：测试节点缓存。
- `.ruff_cache/`：Ruff lint 缓存目录。
- `.ruff_cache/.gitignore`：Ruff 缓存忽略文件。
- `.ruff_cache/0.8.1/`：按 Ruff 版本划分的缓存目录。
- `.ruff_cache/0.8.1/*`：多个哈希命名缓存文件，对应 Ruff 的分析结果。
- `.ruff_cache/CACHEDIR.TAG`：缓存目录标识。
- `.venv/`：本地 Python 虚拟环境目录。
- `.venv/bin/`：虚拟环境命令入口，如 `pytest`、`uvicorn`、`migrate`。
- `.venv/include/`：编译头文件目录。
- `.venv/lib/`：虚拟环境依赖安装目录。
- `CLAUDE.md`：仓库协作约束与架构说明。
- `README.md`：项目部署与运行说明。
- `TODO.md`：当前阶段的整体任务清单与路线图。
- `pyproject.toml`：项目元数据、依赖、脚本入口、Ruff/Mypy/Pytest 配置。
- `uv.lock`：`uv` 依赖锁文件。

## 2. 方案与过程文档目录

- `bug_fix/`：缺陷修复方案目录。
- `bug_fix/user-service/`：`user_service` 问题修复方案子目录。
- `bug_fix/user-service/2026-04-20-audit-fixes.md`：`user_service` 审计问题修复计划。
- `bug_fix/user-service/2026-04-20-full-rebuild-plan.md`：`user_service` 剩余重构实施计划。
- `refactor/`：重构规范与重构草案目录。
- `refactor/user-service.md`：`user_service` 的重构规范文档。

## 3. 部署与运行时目录

- `deploy/`：部署相关文件目录。
- `deploy/.env.example`：部署用环境变量示例。
- `deploy/Dockerfile`：当前统一 Docker 镜像构建文件。
- `deploy/docker-compose.yml`：多服务联调与部署编排文件。
- `deploy/router/`：`router_service` 运行配置目录。
- `deploy/router/model_paths.json`：路由模型权重路径配置。
- `deploy/router/runtime_config.json`：路由运行时打分与模型选择配置。
- `logs/`：本地运行日志目录。
- `logs/access.log`：访问日志。
- `logs/app.log`：应用主日志。
- `logs/error.log`：错误日志。

## 4. 文档目录 `docs/`

- `docs/`：项目正式文档目录。
- `docs/ARCHITECTURE.md`：项目整体架构文档。
- `docs/DATABASE.md`：数据库与表关系文档。
- `docs/Database/`：按业务域拆分的数据库文档目录。
- `docs/Database/user.md`：`user_service` 数据库设计分析。
- `docs/PROJECT_STRUCTURE.md`：当前这份项目目录结构说明文档。
- `docs/phase2-cutover.md`：Phase 2 数据库切换运行手册。
- `docs/phase4-operations.md`：Phase 4 运行时契约与运维手册。
- `docs/router-design.md`：`router_service` 设计文档。
- `docs/schema-ownership.md`：各 schema 所有权说明。
- `docs/service-runtime-contracts.md`：服务运行时契约文档。
- `docs/superpowers/`：superpowers 过程产物目录。
- `docs/superpowers/plans/`：实施计划文档目录。
- `docs/superpowers/plans/2026-04-20-user-service-followup.md`：`user_service` 后续修复实施计划。

## 5. 数据库迁移目录 `migrations/`

- `migrations/`：Alembic 迁移总目录。
- `migrations/README.md`：迁移目录说明文档。
- `migrations/__init__.py`：迁移包初始化文件。
- `migrations/__pycache__/`：迁移模块字节码缓存目录。
- `migrations/_env_shared.py`：多服务迁移共享环境逻辑。
- `migrations/cutover_manifest.json`：Phase 2 切换清单配置。
- `migrations/helpers.py`：迁移辅助工具函数。
- `migrations/admin_service/`：`admin_service` 迁移目录。
- `migrations/admin_service/env.py`：`admin_service` Alembic 环境定义。
- `migrations/admin_service/script.py.mako`：迁移脚本模板。
- `migrations/admin_service/versions/`：`admin_service` 版本迁移目录。
- `migrations/admin_service/versions/20260313_01_admin_baseline.py`：`admin_service` 初始基线迁移。
- `migrations/admin_service/versions/__init__.py`：版本目录初始化文件。
- `migrations/testing_service/`：`testing_service` 迁移目录。
- `migrations/testing_service/env.py`：`testing_service` Alembic 环境定义。
- `migrations/testing_service/script.py.mako`：迁移脚本模板。
- `migrations/testing_service/versions/`：`testing_service` 版本迁移目录。
- `migrations/testing_service/versions/20260313_05_testing_baseline.py`：`testing_service` 初始基线迁移。
- `migrations/testing_service/versions/20260313_06_testing_model_knowledge_cutoff.py`：给测试模型增加知识截止字段的迁移。
- `migrations/testing_service/versions/20260314_01_testing_drop_knowledge_cutoff.py`：删除知识截止字段的迁移。
- `migrations/testing_service/versions/__init__.py`：版本目录初始化文件。
- `migrations/user_service/`：`user_service` 迁移目录。
- `migrations/user_service/__pycache__/`：`user_service` 迁移环境缓存目录。
- `migrations/user_service/env.py`：`user_service` Alembic 环境定义。
- `migrations/user_service/script.py.mako`：迁移脚本模板。
- `migrations/user_service/versions/`：`user_service` 版本迁移目录。
- `migrations/user_service/versions/20260313_02_user_baseline.py`：`user_service` 初始基线迁移。
- `migrations/user_service/versions/20260420_01_drop_user_active_sessions.py`：删除旧 `user_active_sessions` 表相关结构。
- `migrations/user_service/versions/20260420_02_users_add_balance_columns.py`：给 `users` 表增加余额相关字段。
- `migrations/user_service/versions/20260420_03_create_user_api_keys.py`：创建用户 API Key 表。
- `migrations/user_service/versions/20260420_04_create_balance_transactions.py`：创建余额流水表。
- `migrations/user_service/versions/20260420_05_create_topup_orders.py`：创建充值订单表。
- `migrations/user_service/versions/20260420_06_create_api_call_logs.py`：创建 API 调用日志表。
- `migrations/user_service/versions/20260420_07_create_usage_stats.py`：创建用量统计表。
- `migrations/user_service/versions/20260420_08_create_invitation_release_outbox.py`：创建邀请码释放 outbox 表。
- `migrations/user_service/versions/20260420_09_add_local_foreign_keys.py`：补充本地外键约束。
- `migrations/user_service/versions/20260420_10_billing_idempotency_constraints.py`：增加计费幂等约束。
- `migrations/user_service/versions/20260420_11_add_deleted_at_to_user_api_keys.py`：给 API Key 表增加软删除字段。
- `migrations/user_service/versions/__init__.py`：版本目录初始化文件。
- `migrations/user_service/versions/__pycache__/`：`user_service` 迁移版本缓存目录。

## 6. 工程脚本目录 `scripts/`

- `scripts/`：工程脚本总目录。
- `scripts/__init__.py`：脚本包初始化文件。
- `scripts/bootstrap_service_databases.py`：一键初始化多个服务数据库的脚本。
- `scripts/check_service_environment.py`：检查环境变量与运行前置条件。
- `scripts/migrate.py`：Alembic 迁移统一入口脚本。
- `scripts/phase2_cutover.py`：Phase 2 数据库切换执行脚本。
- `scripts/runtime_probe.py`：容器健康探针与依赖探测脚本。
- `scripts/sql/`：SQL 快照与初始化脚本目录。
- `scripts/sql/admin_schema.sql`：`admin_service` schema 快照。
- `scripts/sql/init_tables.sql`：初始化表结构脚本。
- `scripts/sql/testing_schema.sql`：`testing_service` schema 快照。
- `scripts/sql/user_schema.sql`：`user_service` schema 快照。
- `scripts/start_services.py`：本地启动多个服务的统一入口。

## 7. 源码目录 `src/`

- `src/`：项目源码根目录，采用 `src layout`。

### 7.1 聚合应用 `src/backend_app/`

- `src/backend_app/`：聚合控制面应用目录。
- `src/backend_app/__init__.py`：包初始化文件。
- `src/backend_app/__pycache__/`：聚合应用字节码缓存目录。
- `src/backend_app/config.py`：聚合应用配置定义。
- `src/backend_app/main.py`：聚合 FastAPI 应用入口。

### 7.2 共享基础层 `src/common/`

- `src/common/`：跨服务共享能力目录。
- `src/common/__init__.py`：共享包初始化文件。
- `src/common/__pycache__/`：共享包缓存目录。
- `src/common/config.py`：基础配置模型定义。
- `src/common/core/`：全局异常与错误处理目录。
- `src/common/core/__init__.py`：核心包初始化文件。
- `src/common/core/__pycache__/`：核心包缓存目录。
- `src/common/core/exception_handlers.py`：FastAPI 统一异常处理器。
- `src/common/core/exceptions.py`：共享异常类型定义。
- `src/common/db/`：数据库共享封装目录。
- `src/common/db/__init__.py`：数据库包初始化文件。
- `src/common/db/__pycache__/`：数据库包缓存目录。
- `src/common/db/base.py`：ORM 基类、时间戳、雪花 ID mixin。
- `src/common/db/runtime.py`：数据库运行时封装与 session 管理。
- `src/common/health.py`：健康检查响应构造逻辑。
- `src/common/internal.py`：服务间 HMAC 签名请求封装。
- `src/common/models/`：共享模型预留目录，当前无源码文件。
- `src/common/observability.py`：日志与可观测性封装。
- `src/common/services/`：共享服务目录。
- `src/common/services/content/`：内容服务共享逻辑预留目录，当前为空。
- `src/common/services/identity/`：身份服务共享逻辑预留目录，当前为空。
- `src/common/utils/`：共享工具函数目录。
- `src/common/utils/__init__.py`：工具包初始化文件。
- `src/common/utils/__pycache__/`：工具包缓存目录。
- `src/common/utils/crypto.py`：通用加解密工具。
- `src/common/utils/jwt.py`：JWT 生成与校验工具。
- `src/common/utils/openai_compat.py`：OpenAI 兼容层辅助工具。
- `src/common/utils/password.py`：密码哈希辅助工具。
- `src/common/utils/snowflake.py`：雪花 ID 工具。
- `src/common/utils/timezone.py`：时区处理工具。

### 7.3 管理服务 `src/admin_service/`

- `src/admin_service/`：管理员域服务目录。
- `src/admin_service/__init__.py`：包初始化文件。
- `src/admin_service/__pycache__/`：管理员服务缓存目录。
- `src/admin_service/api/`：HTTP API 层目录。
- `src/admin_service/api/__init__.py`：API 包初始化文件。
- `src/admin_service/api/__pycache__/`：API 包缓存目录。
- `src/admin_service/api/v1/`：V1 版本 API 目录。
- `src/admin_service/api/v1/__init__.py`：V1 API 初始化文件。
- `src/admin_service/api/v1/__pycache__/`：V1 API 缓存目录。
- `src/admin_service/api/v1/endpoints/`：管理员服务接口实现目录。
- `src/admin_service/api/v1/endpoints/__init__.py`：接口目录初始化文件。
- `src/admin_service/api/v1/endpoints/__pycache__/`：接口目录缓存。
- `src/admin_service/api/v1/endpoints/admin_audit_logs.py`：管理员审计日志接口。
- `src/admin_service/api/v1/endpoints/admin_users.py`：管理员用户管理接口。
- `src/admin_service/api/v1/endpoints/auth.py`：管理员认证接口。
- `src/admin_service/api/v1/endpoints/internal.py`：对内部服务暴露的管理员查询接口。
- `src/admin_service/api/v1/endpoints/invitation.py`：邀请码相关接口。
- `src/admin_service/api/v1/router.py`：管理员服务路由聚合。
- `src/admin_service/bootstrap_superadmin.py`：超级管理员初始化入口。
- `src/admin_service/config.py`：管理员服务配置。
- `src/admin_service/db.py`：管理员服务数据库运行时与依赖。
- `src/admin_service/dependencies.py`：FastAPI 依赖定义。
- `src/admin_service/exceptions.py`：管理员服务异常定义。
- `src/admin_service/main.py`：管理员服务 FastAPI 入口。
- `src/admin_service/models/`：管理员域 ORM 模型目录。
- `src/admin_service/models/__init__.py`：模型包初始化文件。
- `src/admin_service/models/__pycache__/`：模型包缓存目录。
- `src/admin_service/models/admin_audit_log.py`：管理员审计日志模型。
- `src/admin_service/models/admin_user.py`：管理员用户模型。
- `src/admin_service/models/invitation_code.py`：邀请码模型。
- `src/admin_service/schemas.py`：Pydantic 请求响应模型。
- `src/admin_service/services/`：管理员服务业务逻辑目录。
- `src/admin_service/services/__init__.py`：服务层初始化文件。
- `src/admin_service/services/__pycache__/`：服务层缓存目录。
- `src/admin_service/services/audit_service.py`：审计日志业务逻辑。
- `src/admin_service/services/auth_service.py`：管理员认证逻辑。
- `src/admin_service/services/bootstrap_service.py`：超级管理员引导逻辑。
- `src/admin_service/services/identity_client.py`：调用 `user_service` 身份接口的客户端。
- `src/admin_service/services/invitation_service.py`：邀请码业务逻辑。
- `src/admin_service/services/management_service.py`：管理员管理操作逻辑。
- `src/admin_service/utils/`：管理员服务工具目录。
- `src/admin_service/utils/__init__.py`：工具包初始化文件。
- `src/admin_service/utils/__pycache__/`：工具包缓存目录。
- `src/admin_service/utils/password.py`：管理员密码处理辅助工具。

### 7.4 用户服务 `src/user_service/`

- `src/user_service/`：用户域服务目录。
- `src/user_service/__init__.py`：包初始化文件。
- `src/user_service/__pycache__/`：用户服务缓存目录。
- `src/user_service/api/`：HTTP API 层目录。
- `src/user_service/api/__init__.py`：API 包初始化文件。
- `src/user_service/api/__pycache__/`：API 包缓存目录。
- `src/user_service/api/v1/`：V1 版本 API 目录。
- `src/user_service/api/v1/__init__.py`：V1 API 初始化文件。
- `src/user_service/api/v1/__pycache__/`：V1 API 缓存目录。
- `src/user_service/api/v1/endpoints/`：用户服务接口目录。
- `src/user_service/api/v1/endpoints/__init__.py`：接口目录初始化文件。
- `src/user_service/api/v1/endpoints/__pycache__/`：接口目录缓存。
- `src/user_service/api/v1/endpoints/admin_billing.py`：管理员视角的计费接口。
- `src/user_service/api/v1/endpoints/auth.py`：用户注册、登录、刷新等认证接口。
- `src/user_service/api/v1/endpoints/billing.py`：余额、订单、账单相关接口。
- `src/user_service/api/v1/endpoints/internal.py`：内部服务调用的用户接口。
- `src/user_service/api/v1/endpoints/keys.py`：API Key 管理接口。
- `src/user_service/api/v1/router.py`：用户服务路由聚合。
- `src/user_service/config.py`：用户服务配置。
- `src/user_service/db.py`：用户服务数据库运行时与 session 依赖。
- `src/user_service/dependencies.py`：用户服务 FastAPI 依赖。
- `src/user_service/jobs.py`：异步任务与 job 定义。
- `src/user_service/models/`：用户域 ORM 模型目录。
- `src/user_service/models/__init__.py`：模型包初始化文件。
- `src/user_service/models/__pycache__/`：模型包缓存目录。
- `src/user_service/models/api_call_log.py`：API 调用日志模型。
- `src/user_service/models/balance_transaction.py`：余额流水模型。
- `src/user_service/models/email_verification_code.py`：邮箱验证码模型。
- `src/user_service/models/invitation_release_outbox.py`：邀请码释放 outbox 模型。
- `src/user_service/models/topup_order.py`：充值订单模型。
- `src/user_service/models/usage_stat.py`：用量统计模型。
- `src/user_service/models/user.py`：用户主模型。
- `src/user_service/models/user_api_key.py`：用户 API Key 模型。
- `src/user_service/models/user_session.py`：用户会话模型。
- `src/user_service/schemas.py`：用户服务 Pydantic 模型。
- `src/user_service/services/`：用户服务业务逻辑目录。
- `src/user_service/services/__init__.py`：服务层初始化文件。
- `src/user_service/services/__pycache__/`：服务层缓存目录。
- `src/user_service/services/admin_client.py`：调用 `admin_service` 的客户端。
- `src/user_service/services/api_key_service.py`：API Key 业务逻辑。
- `src/user_service/services/auth_service.py`：用户认证业务逻辑。
- `src/user_service/services/balance_service.py`：余额账本业务逻辑。
- `src/user_service/services/email_service.py`：邮件发送与验证码业务逻辑。
- `src/user_service/services/topup_order_service.py`：充值订单业务逻辑。
- `src/user_service/services/usage_stat_service.py`：用量统计业务逻辑。
- `src/user_service/utils/`：用户服务工具目录。
- `src/user_service/utils/__init__.py`：工具包初始化文件。
- `src/user_service/utils/__pycache__/`：工具包缓存目录。
- `src/user_service/utils/api_key_policy.py`：API Key 策略工具。
- `src/user_service/utils/email.py`：邮箱规范化与邮件工具。
- `src/user_service/utils/password.py`：用户密码处理工具。
- `src/user_service/worker.py`：用户域后台 worker 入口。

### 7.5 测试与基准服务 `src/testing_service/`

- `src/testing_service/`：模型测试与 benchmark 服务目录。
- `src/testing_service/__pycache__/`：测试服务缓存目录。
- `src/testing_service/api/`：HTTP API 层目录。
- `src/testing_service/api/__init__.py`：API 包初始化文件。
- `src/testing_service/api/__pycache__/`：API 包缓存目录。
- `src/testing_service/api/v1/`：V1 版本 API 目录。
- `src/testing_service/api/v1/__init__.py`：V1 API 初始化文件。
- `src/testing_service/api/v1/__pycache__/`：V1 API 缓存目录。
- `src/testing_service/api/v1/endpoints/`：测试服务接口目录。
- `src/testing_service/api/v1/endpoints/__init__.py`：接口目录初始化文件。
- `src/testing_service/api/v1/endpoints/__pycache__/`：接口目录缓存。
- `src/testing_service/api/v1/endpoints/benchmark.py`：Benchmark 提交与查询接口。
- `src/testing_service/api/v1/endpoints/internal_router.py`：面向 `router_service` 的内部接口。
- `src/testing_service/api/v1/endpoints/model_providers.py`：模型与 provider 关联接口。
- `src/testing_service/api/v1/endpoints/models.py`：模型目录接口。
- `src/testing_service/api/v1/endpoints/providers.py`：provider 配置接口。
- `src/testing_service/api/v1/endpoints/vendors.py`：vendor 管理接口。
- `src/testing_service/api/v1/router.py`：测试服务路由聚合。
- `src/testing_service/benchmark/`：Benchmark 执行逻辑目录。
- `src/testing_service/benchmark/__init__.py`：Benchmark 包初始化文件。
- `src/testing_service/benchmark/__pycache__/`：Benchmark 包缓存目录。
- `src/testing_service/benchmark/engine.py`：Benchmark 执行引擎。
- `src/testing_service/benchmark/jobs.py`：Benchmark 任务定义。
- `src/testing_service/benchmark/probe_runner.py`：探测运行器。
- `src/testing_service/benchmark/queue.py`：Benchmark 队列封装。
- `src/testing_service/benchmark/tasks.py`：Benchmark 执行任务。
- `src/testing_service/benchmarking/`：较高层的 benchmark 组织目录。
- `src/testing_service/benchmarking/__init__.py`：包初始化文件。
- `src/testing_service/benchmarking/__pycache__/`：包缓存目录。
- `src/testing_service/benchmarking/schemas.py`：Benchmark 领域模型定义。
- `src/testing_service/benchmarking/services.py`：Benchmark 业务编排逻辑。
- `src/testing_service/catalog/`：模型目录能力预留目录。
- `src/testing_service/catalog/__init__.py`：目录包初始化文件。
- `src/testing_service/catalog/__pycache__/`：目录包缓存目录。
- `src/testing_service/config.py`：测试服务配置。
- `src/testing_service/core/`：测试服务核心组件目录。
- `src/testing_service/core/__init__.py`：核心包初始化文件。
- `src/testing_service/core/cache.py`：测试服务缓存封装。
- `src/testing_service/db.py`：测试服务数据库运行时与依赖。
- `src/testing_service/dependencies.py`：测试服务依赖定义。
- `src/testing_service/main.py`：测试服务 FastAPI 入口，同时可承载 scheduler 模式。
- `src/testing_service/models/`：测试服务 ORM 模型目录。
- `src/testing_service/models/__init__.py`：模型包初始化文件。
- `src/testing_service/models/__pycache__/`：模型包缓存目录。
- `src/testing_service/models/model.py`：模型目录表 ORM 定义。
- `src/testing_service/provider_config/`：provider 配置组织目录。
- `src/testing_service/provider_config/__init__.py`：provider 配置包初始化文件。
- `src/testing_service/provider_config/__pycache__/`：provider 配置缓存目录。
- `src/testing_service/schemas.py`：测试服务 Pydantic 模型。
- `src/testing_service/services/`：测试服务业务逻辑目录。
- `src/testing_service/services/__init__.py`：服务层初始化文件。
- `src/testing_service/services/__pycache__/`：服务层缓存目录。
- `src/testing_service/services/admin_identity_client.py`：调用 `admin_service` 身份接口的客户端。
- `src/testing_service/services/benchmark_job_service.py`：Benchmark 作业业务逻辑。
- `src/testing_service/services/model_service.py`：模型目录业务逻辑。
- `src/testing_service/worker.py`：Benchmark 队列 worker 入口。

### 7.6 路由推理服务 `src/router_service/`

- `src/router_service/`：路由推理服务目录。
- `src/router_service/__init__.py`：包初始化文件。
- `src/router_service/__pycache__/`：路由服务缓存目录。
- `src/router_service/config.py`：路由服务配置。
- `src/router_service/dependencies.py`：路由服务依赖定义。
- `src/router_service/logging.py`：路由服务日志配置。
- `src/router_service/main.py`：路由服务 FastAPI 入口。
- `src/router_service/nn/`：推理与打分模型代码目录。
- `src/router_service/nn/__init__.py`：神经网络子包初始化文件。
- `src/router_service/nn/cg_tabm.py`：核心打分/表模型实现。
- `src/router_service/nn/probe.py`：探测与评分相关逻辑。
- `src/router_service/routers/`：HTTP 路由目录。
- `src/router_service/routers/__init__.py`：路由包初始化文件。
- `src/router_service/routers/chat.py`：聊天补全接口。
- `src/router_service/routers/completions.py`：文本补全接口。
- `src/router_service/routers/meta.py`：元信息与健康类接口。
- `src/router_service/schemas.py`：路由服务 Pydantic 模型。
- `src/router_service/services/`：路由服务业务层目录。
- `src/router_service/services/__init__.py`：服务层初始化文件。
- `src/router_service/services/__pycache__/`：服务层缓存目录。
- `src/router_service/services/identity_client.py`：调用身份相关内部接口的客户端。
- `src/router_service/services/router_engine.py`：路由决策引擎。
- `src/router_service/services/upstream.py`：上游 LLM 调用逻辑。
- `src/router_service/utils/`：路由服务工具目录。
- `src/router_service/utils/__init__.py`：工具包初始化文件。
- `src/router_service/utils/__pycache__/`：工具包缓存目录。
- `src/router_service/utils/input_builder.py`：输入组装工具。
- `src/router_service/utils/runtime_config.py`：运行时配置加载工具。
- `src/router_service/utils/scoring.py`：评分计算工具。
- `src/router_service/utils/text.py`：文本处理工具。

## 8. 测试目录 `tests/`

- `tests/`：pytest 测试目录。
- `tests/__init__.py`：测试包初始化文件。
- `tests/__pycache__/`：测试缓存目录。
- `tests/test_admin.py`：管理员服务基础行为测试。
- `tests/test_admin_management.py`：管理员管理操作测试。
- `tests/test_architecture_boundaries.py`：服务边界与架构约束测试。
- `tests/test_backend_app.py`：聚合应用路由与运行测试。
- `tests/test_benchmark_queue.py`：Benchmark 队列逻辑测试。
- `tests/test_common.py`：公共模块测试。
- `tests/test_internal_contracts.py`：内部 HMAC 合同测试。
- `tests/test_migration_structure.py`：迁移目录结构测试。
- `tests/test_phase2_cutover.py`：Phase 2 切换脚本测试。
- `tests/test_phase4_acceptance.py`：Phase 4 接受性测试。
- `tests/test_phase4_degradation.py`：Phase 4 降级场景测试。
- `tests/test_phase4_runtime.py`：Phase 4 运行时契约测试。
- `tests/test_review_fixes.py`：历史 review 修复回归测试。
- `tests/test_runtime_orchestration.py`：启动编排与容器运行测试。
- `tests/test_runtime_probe.py`：运行时探针脚本测试。
- `tests/test_schema_drift.py`：ORM 与 SQL 快照漂移测试。
- `tests/test_schema_ownership.py`：schema 所有权测试。
- `tests/test_service_environment.py`：环境变量校验测试。
- `tests/test_testing.py`：测试服务领域测试。
- `tests/test_testing_api.py`：测试服务 API 测试。
- `tests/test_user.py`：用户服务核心测试。
- `tests/test_user_rebuild.py`：用户服务重构回归测试。

## 9. 当前结构特点总结

- 业务核心集中在 `src/`，采用 `backend_app + 多独立服务包 + common 共享层` 的组织方式。
- 数据库演进集中在 `migrations/`，并按服务拆分 Alembic 环境。
- 运维、启动、校验逻辑集中在 `scripts/`。
- 设计文档、运行手册、重构方案分散在 `docs/`、`bug_fix/`、`refactor/`。
- `.idea/`、`.pytest_cache/`、`.ruff_cache/`、`.venv/` 属于本地开发或工具运行产物，不属于业务源码，但仍是当前工作区的一部分。
