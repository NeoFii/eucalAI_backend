# Alembic-Only Final Cleanup Design

**Date:** 2026-04-21

**Goal**

把当前项目的数据库 schema 管理彻底收敛到 Alembic：删除运行时建表路径，为每个服务提供独立的 `alembic.ini`，服务启动前显式校验数据库 revision 是否达到目标版本，并顺手清理这轮重构后仍残留的历史测试/文档/入口杂质。

**Non-Goals**

- 不引入新的兼容开关
- 不保留 `AUTO_INIT_DB` 或 `create_all` 兜底路径
- 不改变现有三套服务数据库的 Alembic revision 链
- 不重写现有迁移历史

## Decision

本次采用硬切换：

1. Alembic revision 是唯一 schema 真理
2. 运行时代码不允许再创建/补齐表结构
3. 每个服务拥有自己的 `alembic.ini`
4. `scripts/migrate.py` 只能包装/调度服务级 `alembic.ini`，不能再动态构造第二套配置路径
5. 服务启动前必须检查数据库当前 revision 是否满足 `head`
6. 不满足时直接 fail fast，并给出清晰错误和迁移命令

## Current Problems

虽然文档已经写明 Alembic 是唯一 schema 真理，但代码仍保留第二条 schema 路径：

- `backend_app/lifecycle.py` 仍会根据 `AUTO_INIT_DB` 调 `init_db()`
- `admin_service/main.py`、`testing_service/main.py` 仍有相同逻辑
- `admin_service/bootstrap_superadmin.py` 仍支持 `init_db()` 分支
- `common/db/runtime.py` 仍暴露 `metadata.create_all` 能力

这导致当前系统实际上同时存在两套 schema 生命周期：

- 正式路径：`uv run migrate ...`
- 隐式兜底路径：服务启动时 `create_all`

另外，当前 Alembic 配置仍主要依赖 `scripts/migrate.py` 在运行时动态构造 `Config`。如果后续再引入服务级 `alembic.ini` 却不删这条动态路径，就会把迁移入口变成双轨。

这和当前重构目标冲突，也会让数据库版本状态不可推断。

## Target Design

### 1. Runtime Schema Path

删除所有运行时建表逻辑：

- 删除 `AUTO_INIT_DB` 在服务启动流程中的行为意义
- 删除各服务入口和 `backend_app` 生命周期中对 `init_db()` 的调用
- 如果 `common/db/runtime.py::init_db()` 不再有正当用途，则一并删除
- `bootstrap-super-admin` 不再承担 schema 初始化职责，只负责 super admin 初始化/校验

结果是：**服务进程永远不修改 schema**。

### 2. Startup Revision Check

新增统一的 Alembic revision 检查能力，放在共享脚本/运行时入口可复用的位置。该检查基于服务自己的 `alembic.ini` 和 migration script location 执行，而不是重新拼装第二套动态 Config。

每个服务启动时：

1. 解析该服务自己的数据库 URL
2. 读取数据库当前 revision
3. 读取该服务迁移空间的 `head`
4. 若当前 revision 不是目标 head，立即报错退出

报错信息至少包含：

- service 名称
- 当前数据库 revision
- 目标 head revision
- 推荐修复命令

示例：

`user-service database is at 20260420_09_add_local_foreign_keys, expected head 20260420_11_add_deleted_at_to_user_api_keys; run: uv run migrate --service user-service upgrade head`

### 3. Startup Ownership

各入口职责收敛为：

- `backend_app/lifecycle.py`
  - 初始化 engine / session factory
  - 检查 Alembic revision
  - 执行业务启动动作（如 bootstrap super admin）
  - 不做 schema 初始化
- `admin_service/main.py`
  - standalone admin 运行时也遵守同一规则
- `testing_service/main.py`
  - standalone testing 运行时也遵守同一规则
- `bootstrap_service_databases.py`
  - 成为唯一“一次性把数据库推进到目标版本”的运维入口

### 4. Alembic Configuration Ownership

每个服务都拥有自己独立的 `alembic.ini`，建议位置：

- `migrations/admin_service/alembic.ini`
- `migrations/user_service/alembic.ini`
- `migrations/testing_service/alembic.ini`

这些 ini 文件负责：

- `script_location`
- `prepend_sys_path`
- Alembic logging/config 基础项

`scripts/migrate.py` 的职责收敛为：

- 选择目标服务
- 加载对应 `alembic.ini`
- 在必要时注入数据库 URL 覆盖
- 分发 `upgrade/current/history/heads/revision` 命令

不再允许：

- 在代码里重新手写一整套 Alembic `Config` 作为平行入口
- 让 `scripts/migrate.py` 和服务级 `alembic.ini` 各自描述不同 script_location / sys.path / env 约定

### 5. Configuration Cleanup

`AUTO_INIT_DB` 会变成死配置，最终应删除其运行时含义。

有两种可能：

- 若仅被保留会制造误导，则从配置模型、文档、测试中删除
- 若短期内保留字段成本更低，则字段可暂留，但任何 runtime 代码不得读取它来建表

本次倾向于前者：**直接删除 `AUTO_INIT_DB` 的配置和引用**，避免看起来像“还能自动建表”。

### 6. Final Repository Cleanup

结合前一轮重构中已经发现的遗留问题，这次一起清掉：

- 历史测试中仍引用旧 client / 旧 alias / 旧 schema surface 的断言
- 文档中任何“服务启动时可自动建表”的表述
- 架构测试中仍假设 legacy router / legacy testing alias 的内容
- 运行时和测试代码中对本地 pagination shim 的残余假设

## Files Likely To Change

核心运行时：

- `src/backend_app/lifecycle.py`
- `src/backend_app/main.py`
- `src/admin_service/main.py`
- `src/testing_service/main.py`
- `src/admin_service/bootstrap_superadmin.py`
- `src/common/db/runtime.py`
- `src/common/config.py`
- `src/testing_service/config.py`
- `src/admin_service/db.py`
- `src/user_service/db.py`
- `src/testing_service/db.py`

迁移/脚本：

- `migrations/admin_service/alembic.ini`
- `migrations/user_service/alembic.ini`
- `migrations/testing_service/alembic.ini`
- `scripts/migrate.py`
- `scripts/bootstrap_service_databases.py`
- 可能新增一个共享 revision-check helper

文档：

- `README.md`
- `.env.example`
- `deploy/docker-compose.yml`
- `migrations/README.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/schema-ownership.md`

测试：

- `tests/test_alembic_runtime.py`
- `tests/test_internal_contracts.py`
- `tests/test_phase4_runtime.py`
- `tests/test_migration_structure.py`
- `tests/test_refactor_cleanup.py`
- `tests/test_admin_management.py`
- `tests/test_review_fixes.py`
- 可能补新的 runtime/alembic fail-fast 测试

## Error Handling

失败策略统一为“可诊断的快速失败”：

- engine/session 初始化失败：直接抛出底层错误
- revision 检查失败：抛出明确的 schema version mismatch 错误
- 数据库不可连接：视为 readiness/startup failure，不尝试继续

不允许：

- 自动建表后继续启动
- 自动执行 upgrade
- 静默降级

## Testing Strategy

必须覆盖：

1. 入口文件不再调用 `init_db()` / `create_all`
2. `bootstrap-super-admin` 不再承担 schema 初始化
3. 服务级 `alembic.ini` 是唯一 Alembic 配置入口
4. 启动时会读取并校验 Alembic head
5. revision 不匹配时会 fail fast 且报清晰信息，并阻断后续 bootstrap/scheduler 启动动作
6. 文档和迁移脚本都把 Alembic 作为唯一 schema 入口

回归验证：

- `uv --cache-dir /tmp/uv-cache run pytest tests/ -v`

## Risks

### Risk 1: 开发环境初次启动会失败

这是预期行为，不是 bug。解决方式是先跑迁移。

### Risk 2: 某些测试仍依赖 `AUTO_INIT_DB`

这正是本次最终清理要清掉的对象，不能为了它保留双路径。

### Risk 3: Revision 检查只覆盖 head，不覆盖分支/多 head

当前三套服务迁移链是单 head 线性链，现阶段可以接受。若未来出现多 head，需要在迁移策略层解决，而不是在运行时加兼容。

## Acceptance Criteria

满足以下条件才算完成：

1. 仓库内不再存在运行时 `init_db()` / `create_all` 调用链
2. `src/*/db.py` 不再导出 `init_db`
3. 每个服务都有自己的 `alembic.ini`
4. `scripts/migrate.py` 不再构造平行 Alembic 配置路径
5. 服务启动前会校验 Alembic revision，不满足即失败
6. 文档明确说明：数据库版本只能通过 Alembic 管理
7. 全量测试通过
8. 不通过兼容层维持旧行为
