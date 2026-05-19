# Phase 9: Integration Testing - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

端到端集成测试验证 api-service 所有域协同工作：完整 relay 流程（auth → route → forward → bill → log）、admin 操作传播到 relay 缓存、4 worker 内存约束、Snowflake ID 并发安全。

使用真实 DB/Redis/inference-service 环境，不使用 mock。验证的是模块间集成而非单模块逻辑。

不包含：
- 单元测试补充（已在各 Phase 完成）
- 生产部署验证 — Phase 10
- 前端集成测试 — Phase 10
- 性能压测/基准测试（只做资源约束验证）

</domain>

<decisions>
## Implementation Decisions

### 测试环境策略
- **D-01:** 使用本地真实 MySQL + Redis 服务，专用测试数据库 `eucal_ai_test`
- **D-02:** 连接真实 inference-service（开发环境），不 mock 上游 LLM 调用
- **D-03:** 数据准备使用 Alembic migrate 创建表结构 + pytest fixture seed 测试数据（用户、API Key、路由配置、模型目录、channel 等）
- **D-04:** 测试隔离使用 transaction rollback — 每个 test function 在事务内执行，结束后回滚

### 端到端 relay 流程验证
- **D-05:** 使用 httpx.AsyncClient(transport=ASGITransport(app)) 作为测试客户端，不启动真实 uvicorn 进程
- **D-06:** SSE 流式响应逐 chunk 解析验证：检查 chunk 格式（data: 前缀、JSON 结构）、token 计数累加、末尾 usage 字段、流结束后计费正确
- **D-07:** 三协议全覆盖 — OpenAI Chat Completions、Anthropic Messages、OpenAI Responses，每个协议测试流式 + 非流式
- **D-08:** 验证完整链路状态变化：请求前余额 → 预扣 → 上游调用 → 结算 → call_log 写入 → 最终余额一致

### 内存与并发验证
- **D-09:** 内存测试启动真实 4 worker uvicorn 进程，发送并发请求后用 psutil 采集所有 worker RSS 总和，断言 < 1.5GB
- **D-10:** 内存测试标记 `@pytest.mark.slow`，不在常规 CI 中运行
- **D-11:** Snowflake ID 测试使用多协程并发生成（模拟 4 worker），每个协程生成 10000 个 ID，汇总后 set 去重断言无碰撞
- **D-12:** Snowflake 测试验证 worker_id=1 和 worker_id=2 分别生成的 ID 互不冲突

### Admin→Relay 缓存传播
- **D-13:** 完整链路测试：通过 admin API 修改路由配置 → 验证 Redis routing_config:version 更新 → 发送 relay 请求验证新配置生效
- **D-14:** 时序处理：测试中在 admin 操作后直接调用 RoutingConfigCache.check_version() 强制刷新，不等待自然 poll 周期
- **D-15:** 测试场景包括：新增模型路由、禁用 channel、修改价格 → 验证 relay 端行为相应变化

### Claude's Discretion
- 具体 fixture 数据的值和数量（用户数、Key 数、模型数等）
- 测试文件组织方式（按 plan 分文件 vs 按场景分文件）
- 内存测试的并发请求数量和持续时间
- 是否需要 pytest-timeout 防止测试挂起
- conftest.py 中 DB session 和 Redis 连接的具体 fixture 实现

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 已有测试基础设施
- `services/api-service/tests/conftest.py` — 现有 pytest fixture（mock_user, mock_db, arq_pool_mock），集成测试需要扩展为真实连接
- `services/api-service/tests/test_relay_auth.py` — relay auth 单元测试模式参考
- `services/api-service/tests/test_relay_billing.py` — relay billing 单元测试模式参考
- `services/api-service/tests/test_channel_selector.py` — channel selector 单元测试参考
- `services/api-service/tests/test_config_cache.py` — config cache 单元测试参考

### Relay 完整实现（测试目标）
- `services/api-service/api_service/relay/lifecycle/orchestrator.py` — CallLifecycle 编排器（auth→route→forward→bill→log 全链路）
- `services/api-service/api_service/relay/lifecycle/stream.py` — SSE 流式处理
- `services/api-service/api_service/relay/lifecycle/finalize.py` — 结算/日志完成
- `services/api-service/api_service/relay/config_cache.py` — RoutingConfigCache（version poll 机制）
- `services/api-service/api_service/relay/dependencies.py` — relay 单例管理

### 协议端点（三协议测试入口）
- `services/api-service/api_service/controllers/relay/chat.py` — OpenAI Chat Completions 端点
- `services/api-service/api_service/controllers/relay/anthropic.py` — Anthropic Messages 端点
- `services/api-service/api_service/controllers/relay/responses.py` — OpenAI Responses 端点
- `services/api-service/api_service/controllers/relay/models.py` — GET /v1/models 端点

### Admin 域（缓存传播测试入口）
- `services/api-service/api_service/controllers/admin/` — admin API 路由
- `services/api-service/api_service/services/admin/routing_setting_service.py` — 路由配置 service（写入后更新 version key）

### 配置与启动
- `services/api-service/api_service/core/config.py` — ApiServiceSettings（DB/Redis/inference 连接配置）
- `services/api-service/api_service/core/lifespan.py` — LifespanRegistry（资源初始化顺序）
- `services/api-service/api_service/main.py` — FastAPI app 创建 + 路由挂载

### Architecture
- `docs/architecture-refactoring.md` — 合并架构方案
- `.planning/REQUIREMENTS.md` — DEPL-02 内存约束定义

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `conftest.py` 中的 `make_test_principal()` — 创建 ValidatedApiKey 测试数据，集成测试可复用
- `LifespanRegistry` — 管理资源初始化/关闭顺序，集成测试需要触发完整 lifespan
- `relay/dependencies.py` 的 `init_relay_globals()` — 初始化所有 relay 单例，集成测试需要调用
- Alembic migrations — 已有完整的 schema migration chain，可直接用于测试 DB 初始化

### Established Patterns
- 现有单元测试使用 `AsyncMock` + `MagicMock`，集成测试需要建立新的真实连接 fixture 模式
- `httpx.AsyncClient(transport=ASGITransport(app))` — FastAPI 官方推荐的集成测试方式
- `@pytest.mark.slow` — 标记慢速测试，CI 中可选跳过
- `asyncio.create_task` fire-and-forget — call_log 写入是异步的，测试需要等待完成

### Integration Points
- `api_service.main:app` — ASGI TestClient 的入口
- `eucal_ai_test` 数据库 — 需要在 conftest.py 中配置独立的 DATABASE_URL
- Redis db/0, db/1, db/2 — 测试需要使用独立的 Redis db 或 key prefix 避免污染
- inference-service `http://127.0.0.1:8004` — 真实连接，测试前需确认服务可用

</code_context>

<specifics>
## Specific Ideas

- 集成测试放在独立目录 `tests/integration/` 与现有单元测试分离
- conftest.py 提供真实 DB session（async engine + AsyncSession）和 Redis 连接
- 使用 `pytest-asyncio` 的 session scope fixture 做一次性 Alembic migrate
- SSE 验证可以用 `async for line in response.aiter_lines()` 逐行读取
- 内存测试用 subprocess 启动 uvicorn，测试结束后 kill 进程组
- call_log 异步写入验证：发送请求后 `await asyncio.sleep(0.5)` 等待 create_task 完成，然后查 DB

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 9-Integration Testing*
*Context gathered: 2026-05-19*
