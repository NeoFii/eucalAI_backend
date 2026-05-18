# Requirements: EucalAI Backend Architecture Consolidation

**Defined:** 2026-05-18
**Core Value:** 用户通过 API Key 调用 LLM 转发端点时，请求必须低延迟、高可靠地完成鉴权→路由→转发→计费全链路。

## v1 Requirements

Requirements for the consolidation refactoring. Each maps to roadmap phases.

### Infrastructure (INFRA)

- [ ] **INFRA-01**: api-service 可启动并通过 /health 和 /ready 端点验证
- [ ] **INFRA-02**: 单一 SQLAlchemy async engine 连接合并后的 eucal_ai 数据库
- [ ] **INFRA-03**: Redis 连接池初始化（3 逻辑 DB：session/rate-limit, ARQ, cache）
- [ ] **INFRA-04**: Snowflake ID 生成器在多 worker 进程下无碰撞
- [ ] **INFRA-05**: Alembic baseline 迁移覆盖所有现有表（从两库合并）
- [ ] **INFRA-06**: DB 连接池配置适配 2h4g 服务器（pool_size=5, max_overflow=10/worker）
- [ ] **INFRA-07**: common 层合并（observability, internal HMAC, exceptions, utils）
- [ ] **INFRA-08**: 统一 Settings 配置类（合并三服务配置项）
- [ ] **INFRA-09**: lifespan 正确管理所有资源（DB engine, Redis pools, HTTP clients）

### User Domain (USER)

- [ ] **USER-01**: 用户注册/登录/登出/刷新 token 端点正常工作
- [ ] **USER-02**: User JWT cookie 鉴权（user_access_token）正常工作
- [ ] **USER-03**: API Key CRUD 端点正常工作
- [ ] **USER-04**: 余额查询/交易记录/用量统计端点正常工作
- [ ] **USER-05**: 模型目录公开查询端点正常工作
- [ ] **USER-06**: 邮件服务（注册验证、密码重置）正常工作

### Admin Domain (ADMIN)

- [ ] **ADMIN-01**: 管理员登录/登出/刷新 token 端点正常工作
- [ ] **ADMIN-02**: Admin JWT cookie 鉴权（admin_access_token）正常工作
- [ ] **ADMIN-03**: 用户管理端点直接调用 service 层（不再 HTTP 代理）
- [ ] **ADMIN-04**: Pool/Channel CRUD 端点正常工作
- [ ] **ADMIN-05**: 模型目录 CRUD 端点正常工作
- [ ] **ADMIN-06**: 路由配置管理端点正常工作
- [ ] **ADMIN-07**: 仪表盘统计端点直接调用 service 层（不再 HTTP 代理）
- [ ] **ADMIN-08**: 审计日志端点正常工作
- [ ] **ADMIN-09**: 兑换码管理端点直接调用 service 层（不再 HTTP 代理）
- [ ] **ADMIN-10**: Route Monitor 端点直接调用 service 层（不再 HTTP 代理）
- [ ] **ADMIN-11**: Service Logs 查询端点正常工作
- [ ] **ADMIN-12**: 超管引导初始化正常工作

### Relay Domain (RELAY)

- [ ] **RELAY-01**: POST /v1/chat/completions 端点正常工作（OpenAI Chat 协议）
- [ ] **RELAY-02**: POST /v1/anthropic/messages 端点正常工作（Anthropic Messages 协议）
- [ ] **RELAY-03**: POST /v1/responses 端点正常工作（OpenAI Responses 协议）
- [ ] **RELAY-04**: GET /v1/models 端点返回可用模型列表
- [ ] **RELAY-05**: API Key Bearer 鉴权通过本地 DB + TTLCache 验证（不再 HTTP 调用）
- [ ] **RELAY-06**: 余额检查通过直接 DB 查询（不再 HTTP 调用）
- [ ] **RELAY-07**: RoutingConfigCache 从 DB+Redis 加载路由配置（替代 HTTP 轮询）
- [ ] **RELAY-08**: Admin 修改路由配置时主动失效缓存
- [ ] **RELAY-09**: Call Log 通过 asyncio.create_task 直接写 DB（替代 HTTP 缓冲）
- [ ] **RELAY-10**: 计费扣款通过直接调用 BillingService（不再 HTTP 调用）
- [ ] **RELAY-11**: SSE 流式响应正常工作
- [ ] **RELAY-12**: 三级速率限制正常工作（per-key, per-user, global）
- [ ] **RELAY-13**: Channel 选择 + 熔断器 + 重试逻辑正常工作
- [ ] **RELAY-14**: InferenceClient 远程调用 GPU 服务器分类正常工作

### Internal API (INTL)

- [ ] **INTL-01**: /api/v1/internal/routing-config/* HMAC 签名端点供 inference-service 消费
- [ ] **INTL-02**: inference-service 成功从 api-service 拉取路由配置

### Deployment (DEPL)

- [ ] **DEPL-01**: 数据库从两库合并为单一 eucal_ai 无数据丢失
- [ ] **DEPL-02**: api-service 4 workers 在 2h4g 服务器上内存不超限（<1.5GB）
- [ ] **DEPL-03**: 前端 API_URL 切换后所有功能正常
- [ ] **DEPL-04**: 旧服务停止后无功能回归

## v2 Requirements

Deferred to post-consolidation.

### Protocol Expansion
- **PROTO-01**: Google Gemini 协议适配器
- **PROTO-02**: Mistral 协议适配器
- **PROTO-03**: Image/Audio/Embedding relay 支持

### Advanced Features
- **ADV-01**: 语义缓存（相似请求复用响应）
- **ADV-02**: 分布式追踪（OpenTelemetry）
- **ADV-03**: 订阅制计费模型
- **ADV-04**: 用户组定价

## Out of Scope

| Feature | Reason |
|---------|--------|
| 多租户/组织架构 | 当前单租户足够，复杂度高 |
| 插件系统 | 过度工程化，当前不需要 |
| Chat Playground UI | 前端功能，不在后端重构范围 |
| 新功能开发 | 本次纯重构，feature parity 为目标 |
| 数据库 schema 变更 | 合并库但不改表结构 |
| inference-service 内部逻辑变更 | 只改 URL 指向 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |
| INFRA-06 | Phase 1 | Pending |
| INFRA-07 | Phase 1 | Pending |
| INFRA-08 | Phase 1 | Pending |
| INFRA-09 | Phase 1 | Pending |
| USER-01 | Phase 2 | Pending |
| USER-02 | Phase 2 | Pending |
| USER-03 | Phase 2 | Pending |
| USER-04 | Phase 2 | Pending |
| USER-05 | Phase 2 | Pending |
| USER-06 | Phase 2 | Pending |
| ADMIN-01 | Phase 2 | Pending |
| ADMIN-02 | Phase 2 | Pending |
| ADMIN-03 | Phase 2 | Pending |
| ADMIN-04 | Phase 2 | Pending |
| ADMIN-05 | Phase 2 | Pending |
| ADMIN-06 | Phase 2 | Pending |
| ADMIN-07 | Phase 2 | Pending |
| ADMIN-08 | Phase 2 | Pending |
| ADMIN-09 | Phase 2 | Pending |
| ADMIN-10 | Phase 2 | Pending |
| ADMIN-11 | Phase 2 | Pending |
| ADMIN-12 | Phase 2 | Pending |
| RELAY-01 | Phase 3 | Pending |
| RELAY-02 | Phase 3 | Pending |
| RELAY-03 | Phase 3 | Pending |
| RELAY-04 | Phase 3 | Pending |
| RELAY-05 | Phase 3 | Pending |
| RELAY-06 | Phase 3 | Pending |
| RELAY-07 | Phase 3 | Pending |
| RELAY-08 | Phase 3 | Pending |
| RELAY-09 | Phase 3 | Pending |
| RELAY-10 | Phase 3 | Pending |
| RELAY-11 | Phase 3 | Pending |
| RELAY-12 | Phase 3 | Pending |
| RELAY-13 | Phase 3 | Pending |
| RELAY-14 | Phase 3 | Pending |
| INTL-01 | Phase 4 | Pending |
| INTL-02 | Phase 4 | Pending |
| DEPL-01 | Phase 5 | Pending |
| DEPL-02 | Phase 5 | Pending |
| DEPL-03 | Phase 5 | Pending |
| DEPL-04 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 45 total
- Mapped to phases: 45
- Unmapped: 0

---
*Requirements defined: 2026-05-18*
*Last updated: 2026-05-18 after initial definition*
