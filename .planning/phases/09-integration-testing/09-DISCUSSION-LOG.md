# Phase 9: Integration Testing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 9-Integration Testing
**Areas discussed:** 测试环境策略, 端到端 relay 流程验证方式, 内存与并发验证方法, Admin→Relay 缓存传播测试

---

## 测试环境策略

### DB/Redis 环境

| Option | Description | Selected |
|--------|-------------|----------|
| 本地真实服务 | 直接连接开发机上已运行的 MySQL + Redis，用专用 test 数据库 | ✓ |
| Docker Compose 临时容器 | 用 docker-compose.test.yml 启动临时 MySQL + Redis 容器 | |
| TestContainers | 用 pytest-testcontainers 自动管理容器生命周期 | |

**User's choice:** 本地真实服务
**Notes:** 开发机已有 MySQL + Redis 运行，无需额外容器开销

### 上游 LLM 调用

| Option | Description | Selected |
|--------|-------------|----------|
| Mock inference-service 响应 | 用 httpx mock 或 respx 拦截到 inference-service 的 HTTP 调用 | |
| 启动 stub 服务 | 启动一个轻量的 FastAPI stub 服务模拟 inference-service | |
| 真实 inference-service | 连接真实的 inference-service（开发环境） | ✓ |

**User's choice:** 真实 inference-service
**Notes:** 用户选择完全真实的集成环境

### 数据准备

| Option | Description | Selected |
|--------|-------------|----------|
| Alembic + fixture seed + transaction rollback | 测试前 migrate + seed，每个 test 用事务回滚隔离 | ✓ |
| SQL dump 快照 | 维护一个 SQL dump 文件作为测试数据快照 | |
| 复用开发数据 | 直接使用开发环境现有数据 | |

**User's choice:** Alembic + fixture seed + transaction rollback

---

## 端到端 relay 流程验证方式

### 测试客户端

| Option | Description | Selected |
|--------|-------------|----------|
| ASGI TestClient | httpx.AsyncClient(transport=ASGITransport(app))，不启动真实服务器 | ✓ |
| 真实 uvicorn 进程 | 启动真实 uvicorn 进程（单 worker），用 httpx 通过 HTTP 调用 | |
| 混合方案 | 大部分用 ASGI TestClient，内存/并发测试用真实 uvicorn | |

**User's choice:** ASGI TestClient

### SSE 验证

| Option | Description | Selected |
|--------|-------------|----------|
| 逐 chunk 解析 + 计费验证 | 逐 chunk 解析 SSE 响应，验证格式、token 计数、usage 字段、计费正确 | ✓ |
| 只验证最终状态 | 只验证请求成功、call_log 写入、余额变化 | |

**User's choice:** 逐 chunk 解析 + 计费验证

### 协议覆盖

| Option | Description | Selected |
|--------|-------------|----------|
| 三协议全覆盖 | OpenAI Chat + Anthropic Messages + OpenAI Responses，每个测流式+非流式 | ✓ |
| 只测主协议 | 只测 OpenAI Chat | |
| 测两个主要协议 | OpenAI Chat + Anthropic Messages | |

**User's choice:** 三协议全覆盖

---

## 内存与并发验证方法

### 内存测试

| Option | Description | Selected |
|--------|-------------|----------|
| 真实多 worker + psutil 采集 | 启动 4 worker uvicorn，发送并发请求后用 psutil 采集 RSS 总和 | ✓ |
| 单 worker 估算 | 单 worker 测量内存乘以 4 估算 | |
| 手动验证脚本 | 不在自动化测试中验证，只写手动执行脚本 | |

**User's choice:** 真实多 worker + psutil 采集

### Snowflake ID 测试

| Option | Description | Selected |
|--------|-------------|----------|
| 多协程并发生成 + 去重断言 | 4 个并发协程各生成 10000 个 ID，set 去重断言无碰撞 | ✓ |
| 多进程写入 + 汇总检查 | 启动真实多进程，每个进程生成 ID 写入共享文件 | |

**User's choice:** 多协程并发生成 + 去重断言

---

## Admin→Relay 缓存传播测试

### 传播验证策略

| Option | Description | Selected |
|--------|-------------|----------|
| 完整链路测试 | admin API 修改 → poll → relay 验证新配置生效 | ✓ |
| 直接操作 DB/Redis 触发 reload | 跳过 admin API 层，直接操作底层数据 | |
| 分段验证 | 分开测试 admin→version 和 version→cache reload | |

**User's choice:** 完整链路测试

### 时序处理

| Option | Description | Selected |
|--------|-------------|----------|
| 强制刷新（不等待 poll） | 测试中直接调用 RoutingConfigCache.check_version() 强制刷新 | ✓ |
| 等待自然 poll 周期 | 等待真实的 poll 周期触发 | |

**User's choice:** 强制刷新

---

## Claude's Discretion

- 具体 fixture 数据的值和数量
- 测试文件组织方式
- 内存测试的并发请求数量和持续时间
- 是否需要 pytest-timeout 防止测试挂起
- conftest.py 中 DB session 和 Redis 连接的具体 fixture 实现

## Deferred Ideas

None — discussion stayed within phase scope
