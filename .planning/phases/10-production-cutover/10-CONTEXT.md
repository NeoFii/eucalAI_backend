# Phase 10: Production Cutover - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

将生产流量从旧 4 服务架构切换到新 2 服务架构。包括：数据库合并（eucal_ai_user + eucal_ai_admin → eucal_ai）、前端 API_URL 切换、旧服务停止。

当前为测试环境，无生产流量，切换流程简化为一次性替换。

不包含：
- 新功能开发（纯运维操作阶段）
- 数据库 schema 变更（合并但不改表结构，字段类型升级在 baseline migration 已处理）
- inference-service 内部逻辑变更（Phase 8 已完成 URL 指向更新）
- 性能压测（Phase 9 已验证内存约束）

</domain>

<decisions>
## Implementation Decisions

### 数据库合并策略
- **D-01:** 新库建表 + 逻辑复制方式——先用 Alembic baseline 在 `eucal_ai` 建表，然后用 INSERT INTO ... SELECT 从旧库拉数据
- **D-02:** 纯 SQL 脚本实现迁移（.sql 文件），不依赖 Python 环境，字段转换写在 SQL 表达式中（如 balance*10000 微元转换）
- **D-03:** 停机迁移——低峰时段停止旧服务写入后执行迁移，允许几分钟停机
- **D-04:** 数据校验采用行数 + 关键字段校验——每张表 COUNT(*) 对比 + 关键表（users, api_keys, transactions）做 SUM/MAX 校验确保金额转换正确

### 流量切换流程
- **D-05:** 测试环境一次性替换——停旧服务 → DB 迁移 → 启新服务 → 验证，无需灰度或并行运行
- **D-06:** 前端通过修改 API_URL 环境变量切换到新服务地址
- **D-07:** api-service 使用 :8000 端口（与旧 user-service 一致），admin 端点合并到同一服务不再需要 :8001

### 旧服务下线与监控
- **D-08:** 手动验证后直接停止旧服务——新服务启动后手动测试关键流程（登录、Key 管理、relay 调用、admin 操作），确认 OK 后停旧服务
- **D-09:** 写健康检查脚本作为切换后验证工具——curl 关键端点 + 检查响应状态码和关键字段，未来上线时也可复用
- **D-10:** 测试环境不要求 24h 监控（ROADMAP 的 24h 要求适用于未来生产上线）

### 部署脚本与自动化
- **D-11:** 主控 Shell 脚本（cutover.sh）编排全流程——按顺序执行：停旧服务 → DB 迁移 → 启新服务 → 健康检查，每步有错即停
- **D-12:** 为 api-service 新建 Dockerfile + docker-compose.yml，替代旧的三个服务配置
- **D-13:** 自动合并旧 .env 文件——从 user-service/.env + admin-service/.env + router-service/.env 提取变量，生成 api-service 的统一 .env
- **D-14:** 更新 infra/docker-compose.yml——去掉两个 init-db.sql 挂载，改为单库 eucal_ai 初始化

### Claude's Discretion
- SQL 迁移脚本中具体的字段映射细节（哪些字段需要转换、哪些直接复制）
- 健康检查脚本的具体端点列表和检查逻辑
- Dockerfile 的具体构建步骤（multi-stage build 等）
- cutover.sh 的错误处理和回滚逻辑细节
- .env 合并脚本的变量名映射规则

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 数据库结构（迁移源和目标）
- `services/api-service/migrations/versions/20260519_baseline.py` — 目标 schema（22 张表完整定义），迁移目标参考
- `services/user-service/migrations/versions/20260423_01_user_baseline.py` — 旧 user 库 schema（源表结构，注意 balance 是 INT 分）
- `services/admin-service/migrations/versions/20260501_baseline.py` — 旧 admin 库 schema（源表结构）
- `services/user-service/init-db.sql` — 旧库名 `eucal_ai_user`
- `services/admin-service/init-db.sql` — 旧库名 `eucal_ai_admin`

### 后续迁移（字段变更记录）
- `services/user-service/migrations/versions/20260430_02_monetary_precision.py` — 金额精度变更历史
- `services/user-service/migrations/versions/20260514_01_table_design_fixes.py` — 表设计修复
- `services/admin-service/migrations/versions/20260514_normalize_price_columns.py` — 价格列标准化

### 部署配置（现有参考）
- `infra/docker-compose.yml` — 基础设施（MySQL + Redis），需更新 init-db 挂载
- `services/user-service/docker-compose.yml` — 旧 user-service 部署配置（:8000, 2 workers）
- `services/admin-service/docker-compose.yml` — 旧 admin-service 部署配置（:8001, 2 workers）
- `services/router-service/docker-compose.yml` — 旧 router-service 部署配置（:8003, 4 workers）
- `services/user-service/Dockerfile` — 旧 Dockerfile 模板参考
- `services/inference-service/docker-compose.yml` — inference-service 配置（不变，仅参考）

### 环境变量（合并源）
- `services/user-service/.env` — USER_DATABASE_URL 等用户域变量
- `services/admin-service/.env` — ADMIN_DATABASE_URL 等管理域变量
- `services/api-service/api_service/core/config.py` — ApiServiceSettings 统一配置类（目标变量名参考）

### Architecture
- `docs/architecture-refactoring.md` — 合并架构方案（部署拓扑图）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/api-service/api_service/core/config.py` — ApiServiceSettings 已定义所有需要的环境变量，.env 合并脚本可以此为目标模板
- `services/api-service/migrations/` — Alembic 已配置好，baseline migration 可直接用于新库建表
- `services/*/docker-compose.yml` — 现有 Dockerfile 模板可参考构建步骤
- `services/api-service/api_service/core/lifespan.py` — LifespanRegistry 管理资源初始化，健康检查可验证 lifespan 正常

### Established Patterns
- 各服务使用 uvicorn `--workers N` 多进程模式
- Docker 健康检查使用 `scripts/runtime_probe.py http-ready --port XXXX`
- 环境变量通过 pydantic-settings 加载，有默认值兜底
- Alembic migration 使用 raw SQL（op.execute）而非 ORM 操作

### Integration Points
- `infra/docker-compose.yml` — MySQL 初始化脚本挂载点需更新
- 前端 API_URL 环境变量 — 切换指向
- inference-service `API_SERVICE_URL` — Phase 8 已准备好，切换时配置即可
- Redis 数据无需迁移（session/cache 可重建）

</code_context>

<specifics>
## Specific Ideas

- 迁移脚本应该是幂等的——可以重复执行不会出错（INSERT IGNORE 或先 TRUNCATE 目标表）
- 健康检查脚本覆盖：/health、用户登录、API Key 验证、admin 登录、relay 端点（如果 inference-service 可用）
- cutover.sh 应该有 --dry-run 模式，只打印要执行的步骤不实际执行
- .env 合并时需要处理变量名映射（如 USER_DATABASE_URL → DATABASE_URL）

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-Production Cutover*
*Context gathered: 2026-05-20*
