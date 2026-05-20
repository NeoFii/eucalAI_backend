# Phase 10: Production Cutover - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 10-production-cutover
**Areas discussed:** 数据库合并策略, 流量切换流程, 旧服务下线与监控, 部署脚本与自动化

---

## 数据库合并策略

### Q1: 数据库合并方式

| Option | Description | Selected |
|--------|-------------|----------|
| 新库建表 + 逻辑复制 | 先在新库建表（Alembic baseline），然后用 INSERT INTO ... SELECT 从旧库拉数据，过程中做字段转换 | ✓ |
| ALTER + RENAME TABLE | 直接在旧库上 ALTER TABLE 改字段类型，然后逐表 RENAME TABLE 到新库 | |
| 已合并，只需验证 | 生产环境实际上已经是合并后的 schema | |

**User's choice:** 新库建表 + 逻辑复制
**Notes:** 可控性强，支持字段转换（如 balance INT→BIGINT 微元）

### Q2: 迁移脚本形式

| Option | Description | Selected |
|--------|-------------|----------|
| Python 迁移脚本 | 用 SQLAlchemy 连接新旧库，逐表 SELECT → 转换 → INSERT | |
| 纯 SQL 脚本 | .sql 文件，INSERT INTO eucal_ai.table SELECT ... FROM eucal_ai_user.table | ✓ |
| You decide | Claude 决定 | |

**User's choice:** 纯 SQL 脚本
**Notes:** 轻量，无需 Python 环境，字段转换写在 SQL 表达式里

### Q3: 是否允许停机

| Option | Description | Selected |
|--------|-------------|----------|
| 停机迁移（几分钟） | 迁移前停止旧服务写入，确保数据不再变化后再复制 | ✓ |
| 在线迁移 + binlog 同步 | 不停旧服务，先复制存量，binlog 同步增量，最后瞬间切换 | |
| 低峰停机迁移 | 选凌晨低峰时段停机 | |

**User's choice:** 停机迁移（几分钟）
**Notes:** 简单可靠，用户量小可接受

### Q4: 数据校验策略

| Option | Description | Selected |
|--------|-------------|----------|
| 行数对比即可 | 每张表 COUNT(*) 旧库 vs 新库必须一致 | |
| 行数 + 关键字段校验 | 除行数外，关键表做 SUM/MAX 校验确保金额转换正确 | ✓ |
| You decide | Claude 决定 | |

**User's choice:** 行数 + 关键字段校验
**Notes:** 确保金额转换（balance*10000）正确

---

## 流量切换流程

### Q1: 切换策略

**User's choice:** 直接换（测试环境无生产流量）
**Notes:** 当前还没有上线运行，无需灰度或并行验证

### Q2: 切换流程

| Option | Description | Selected |
|--------|-------------|----------|
| 一次性替换 | 停旧服务 → DB 迁移 → 启新服务 → 改前端配置 → 验证 | ✓ |
| 并行验证后替换 | 新旧并行跑（不同端口），手动验证后再停旧的 | |

**User's choice:** 一次性替换
**Notes:** 测试环境简单直接

### Q3: 前端切换方式

| Option | Description | Selected |
|--------|-------------|----------|
| 前端改 API_URL 环境变量 | 前端代码有 API_URL 环境变量，改为新服务地址 | ✓ |
| 端口不变，前端零改动 | api-service 用 :8000 和旧 user-service 一样 | |
| You decide | Claude 决定 | |

**User's choice:** 前端改 API_URL 环境变量
**Notes:** 明确切换，便于回滚

---

## 旧服务下线与监控

### Q1: 下线策略

| Option | Description | Selected |
|--------|-------------|----------|
| 手动验证后直接停 | 新服务启动后手动测试关键流程，确认 OK 后停旧服务 | ✓ |
| 自动化验证脚本 + 停服务 | 写脚本调用关键 API 端点，跑通后停旧服务 | |
| You decide | Claude 决定 | |

**User's choice:** 手动验证后直接停
**Notes:** 测试环境不需要 24h 监控

### Q2: 验证方式

| Option | Description | Selected |
|--------|-------------|----------|
| 写健康检查脚本 | curl 关键端点 + 检查响应，未来上线也能复用 | ✓ |
| 复用 Phase 9 测试 | 用集成测试套件作为验证手段 | |
| You decide | Claude 决定 | |

**User's choice:** 写健康检查脚本
**Notes:** 轻量且可复用

---

## 部署脚本与自动化

### Q1: 切换过程组织形式

| Option | Description | Selected |
|--------|-------------|----------|
| 主控 Shell 脚本 | cutover.sh 按顺序执行全流程，每步有错即停 | ✓ |
| 手动 Runbook 文档 | 步骤文档，手动执行每条命令 | |
| 更新 docker-compose | docker compose up -d 一键启动新架构 | |

**User's choice:** 主控 Shell 脚本
**Notes:** 自动化但可控

### Q2: 容器化部署

| Option | Description | Selected |
|--------|-------------|----------|
| 新建 Dockerfile + compose | 为 api-service 写新的 Dockerfile 和 docker-compose.yml | ✓ |
| 复用现有模板微调 | 基于 user-service Dockerfile 改路径和服务名 | |
| You decide | Claude 决定 | |

**User's choice:** 新建 Dockerfile + compose
**Notes:** 干净起步，替代旧的三个服务配置

### Q3: 环境变量迁移

| Option | Description | Selected |
|--------|-------------|----------|
| 写 .env.example 模板 | 列出所有需要的环境变量供手动填写 | |
| 自动合并旧 .env | 从旧服务 .env 文件提取并合并生成新的 .env | ✓ |
| You decide | Claude 决定 | |

**User's choice:** 自动合并旧 .env
**Notes:** 减少手动操作，处理变量名映射

---

## Claude's Discretion

- SQL 迁移脚本中具体的字段映射细节
- 健康检查脚本的具体端点列表和检查逻辑
- Dockerfile 的具体构建步骤
- cutover.sh 的错误处理和回滚逻辑细节
- .env 合并脚本的变量名映射规则

## Deferred Ideas

None — discussion stayed within phase scope
