# Phase 7: Protocol Adapters & Streaming - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

三个协议端点（OpenAI Chat Completions、Anthropic Messages、OpenAI Responses）的完整请求处理链路——从接收请求到返回响应（含 SSE 流式），加上三级速率限制（per-key/per-user/global）和 GET /v1/models 模型列表端点。

Phase 6 已完成的基础设施（直接调用）：
- API Key 本地鉴权（Redis 缓存 + DB fallback）
- 预扣费/结算/退款计费模型（RelayBillingService）
- 路由配置缓存（RoutingConfigCache 进程内单例）
- Call Log 两步直写 DB（asyncio.create_task fire-and-forget）
- Channel 选择器（weighted round-robin + cooldown + auto-disable + affinity）
- InferenceClient HTTP 调用（到 GPU 服务器）

本阶段构建协议层：将用户请求解析为统一格式 → 调用上游 SDK → 将响应转换回协议格式 → SSE 流式输出。

不包含：
- inference-service HMAC 内部端点 — Phase 8
- 端到端集成测试 — Phase 9
- 生产部署切换 — Phase 10

</domain>

<decisions>
## Implementation Decisions

### CallLifecycle 移植策略
- **D-01:** 保留 CallLifecycle 类作为统一编排器，内部调用 Phase 6 已有模块（relay.auth / relay.billing / relay.routing / relay.call_log_writer）
- **D-02:** 拆分到 `relay/lifecycle/` 目录：orchestrator.py（主编排 + execute 入口）、stream.py（流式处理）、finalize.py（结算/日志完成）。每个文件 <200 行
- **D-03:** 借鉴 new-api 重试模式——重试循环在 lifecycle.execute() 层级，每次重试重新调用 ChannelSelector 选择新 channel（排除已失败的）。不再把重试封装在 upstream_caller 内部
- **D-04:** 重试次数从 settings.CHANNEL_MAX_RETRIES 读取（默认 2 次）

### SDK Client Pool + 上游调用
- **D-05:** 原样移植 SdkClientPool（threading.Lock + LRU OrderedDict，max_size=64）到 api-service
- **D-06:** SdkClientPool 在 lifespan 初始化，通过 relay/dependencies.py 暴露 get_sdk_client_pool()
- **D-07:** upstream_dispatch 保持原有路由逻辑：根据 provider_slug 分派到 openai/anthropic 后端
- **D-08:** SdkClientPool.close_all() 在 lifespan shutdown 时调用

### SSE 流式响应处理
- **D-09:** 借鉴 new-api Adaptor 模式 + 保留双路径设计：
  - 路径 1（默认）：OpenAI 格式流——SDK 返回结构化 chunk → StreamConverter 转换为目标协议格式 → SSE 输出
  - 路径 2（特殊）：Anthropic 原生透传——当上游是 Anthropic 且入站协议也是 Anthropic 时，直接转发 SDK 事件（保留原生 event type）
- **D-10:** 流迭代逻辑统一在 lifecycle/stream.py 中，StreamConverter 只负责 chunk 格式转换（轻量接口）
- **D-11:** stream_options.include_usage 默认注入（与原 router-service 行为一致），确保流式响应末尾包含 usage 信息用于计费
- **D-12:** 流式中断处理：client disconnect → GeneratorExit/CancelledError → finalize 中标记 status=499；上游错误 → 标记 status=502

### 三级速率限制实现
- **D-13:** 三级统一使用 token bucket 算法（单一 Lua 脚本），不再混用 sliding window
- **D-14:** 检查顺序：global → per-user → per-key（大到小，早拒绝减少 Redis 调用）
- **D-15:** per-key RPM 从 token 缓存读取 rpm_limit 字段（Phase 6 D-02 已缓存）；per-user RPM 从 RoutingConfigCache 读取 default_user_rpm；global RPM 从 settings 读取
- **D-16:** InMemory fallback 保留——Redis 不可用时用 cachetools.TTLCache 降级（与原 router-service 一致）
- **D-17:** 限流作为 FastAPI Depends 注入（类似 new-api middleware 模式），在 CallLifecycle.execute() 之前执行
- **D-18:** 参考 new-api 的 token bucket Lua 脚本实现（HMSET tokens/last_time + 容量/速率计算）

### GET /v1/models 端点
- **D-19:** 基于用户权限过滤——从 RoutingConfigCache 读取全量模型列表，结合 token 缓存中的 allowed_models 字段过滤，返回 OpenAI 格式的 model list
- **D-20:** 如果 token 的 allowed_models 为空（不限制），返回全量可用模型

### Claude's Discretion
- ProtocolAdapter 的具体方法签名和内部组织由 planner 决定
- Anthropic Messages adapter 的 parse_request 实现细节（如何处理 system prompt、thinking 等）
- 非流式响应的具体字段清理逻辑（strip_think_tags 等）
- 429 响应的 Retry-After header 计算方式
- /v1/models 响应中的 model metadata 字段（id, object, created, owned_by）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Router-Service 源码（移植源 — 协议层权威参考）
- `services/router-service/src/controllers/chat.py` — OpenAI Chat 端点入口
- `services/router-service/src/controllers/responses.py` — OpenAI Responses 端点入口
- `services/router-service/src/services/protocol_adapter.py` — ProtocolAdapter + StreamConverter Protocol 定义
- `services/router-service/src/services/adapters/openai_chat.py` — OpenAI Chat adapter 完整实现
- `services/router-service/src/services/adapters/anthropic_messages.py` — Anthropic Messages adapter
- `services/router-service/src/services/adapters/openai_responses.py` — OpenAI Responses adapter
- `services/router-service/src/services/call_lifecycle.py` — CallLifecycle 8 阶段编排器（642 行，移植主体）
- `services/router-service/src/services/upstream_dispatch.py` — SDK 路由分派逻辑
- `services/router-service/src/services/upstream_caller.py` — 上游调用 + 重试（重试逻辑将提升到 lifecycle 层）
- `services/router-service/src/services/sdk_clients.py` — SdkClientPool LRU 实现
- `services/router-service/src/services/rate_limiter.py` — RateLimiter 三级限流（134 行）
- `services/router-service/src/services/lua/token_bucket.lua` — Token bucket Lua 脚本
- `services/router-service/src/services/lua/sliding_window.lua` — Sliding window Lua 脚本（参考但不使用）
- `services/router-service/src/schemas/anthropic.py` — Anthropic 请求/响应 schema
- `services/router-service/src/schemas/responses.py` — OpenAI Responses 请求/响应 schema
- `services/router-service/src/services/anthropic_backend.py` — Anthropic SDK 调用封装
- `services/router-service/src/services/anthropic_convert.py` — OpenAI→Anthropic 消息转换
- `services/router-service/src/services/responses_convert.py` — Responses 协议转换

### new-api 参考实现（架构模式参考）
- `/root/autodl-tmp/new-api-main/controller/relay.go` — 重试循环在 controller 层的模式（借鉴）
- `/root/autodl-tmp/new-api-main/relay/channel/adapter.go` — Adaptor 接口设计（参考）
- `/root/autodl-tmp/new-api-main/common/limiter/lua/rate_limit.lua` — Token bucket Lua 脚本（借鉴）
- `/root/autodl-tmp/new-api-main/middleware/model-rate-limit.go` — 模型级限流 middleware 模式（借鉴）
- `/root/autodl-tmp/new-api-main/service/pre_consume_quota.go` — PreConsumeQuota + trustQuota（Phase 6 已实现）

### Phase 6 产出（已就绪 — 直接调用）
- `services/api-service/api_service/relay/auth.py` — API Key 鉴权（Redis 缓存 + DB fallback）
- `services/api-service/api_service/relay/billing.py` — RelayBillingService（预扣/结算/退款）
- `services/api-service/api_service/relay/routing.py` — route_and_resolve() 路由编排
- `services/api-service/api_service/relay/call_log_writer.py` — CallLogWriter 两步直写
- `services/api-service/api_service/relay/channel_selector.py` — ChannelSelector
- `services/api-service/api_service/relay/channel_affinity.py` — ChannelAffinityStore
- `services/api-service/api_service/relay/config_cache.py` — RoutingConfigCache
- `services/api-service/api_service/relay/inference_client.py` — InferenceClient
- `services/api-service/api_service/relay/dependencies.py` — relay 单例管理（init_relay_globals + get_*）
- `services/api-service/api_service/relay/upstream.py` — resolve_model_channel_target

### Architecture
- `docs/architecture-refactoring.md` — 合并架构方案

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `relay/auth.py` — require_api_key dependency，返回 ValidatedApiKey（含 user_id, balance, rpm_limit, allowed_models）
- `relay/billing.py` — RelayBillingService.pre_consume() / settle() / refund()
- `relay/routing.py` — route_and_resolve() 返回 (selected_model, target_info, route_result, route_meta)
- `relay/call_log_writer.py` — CallLogWriter.create() / update()（asyncio.create_task 内部）
- `relay/config_cache.py` — RoutingConfigCache.load() 返回完整配置 dict（含 model_channels, model_prices, user_facing_aliases）
- `relay/dependencies.py` — get_routing_config_cache() / get_channel_selector() / get_inference_client()
- `common/observability.py` — log_event 结构化日志
- `common/utils/snowflake.py` — Snowflake ID 生成

### Established Patterns
- Service @staticmethod + `db: AsyncSession` 首参
- asyncio.create_task fire-and-forget（Phase 4 email, Phase 6 call_log）
- FastAPI Depends 注入鉴权/限流
- relay 单例通过 module-level getter 访问（不用 DI container）
- 配置从 `core.config.settings` 单例读取

### Integration Points
- `api_service/core/lifespan.py` — 注册 SdkClientPool 初始化/关闭
- `api_service/core/router.py` — 挂载 relay 端点路由（/v1/chat/completions, /v1/anthropic/messages, /v1/responses, /v1/models）
- Redis db/2 — 限流 key（rl:global, rl:user:{id}, rl:key:{key_hash}）
- Phase 6 relay 模块 — CallLifecycle 内部直接 import 调用

</code_context>

<specifics>
## Specific Ideas

- 整体对标 new-api 设计，哪里做得更好就借鉴哪里
- 重试循环提升到 lifecycle 层（借鉴 new-api controller/relay.go 的 for 循环模式）
- Token bucket Lua 脚本参考 new-api 的 `common/limiter/lua/rate_limit.lua`（HMSET tokens/last_time 模式）
- 限流作为 Depends 注入，类似 new-api 的 middleware 前置模式
- Anthropic 原生透传保留——避免 Anthropic→OpenAI→Anthropic 双重转换的性能损耗和信息丢失
- ProtocolAdapter 保持轻量（只负责格式转换），不像 new-api Adaptor 那样包含 DoRequest（因为我们用 Python SDK 而非裸 HTTP）

</specifics>

<deferred>
## Deferred Ideas

- **Responses 协议的 background mode**：OpenAI Responses API 支持 background 异步执行，当前不实现
- **WebSocket realtime 协议**：new-api 支持 OpenAI Realtime API（WebSocket），当前不在 scope
- **per-model 限流**：new-api 支持按模型维度限流，当前只做 per-key/per-user/global 三级
- **限流的动态配置热更新**：当前 global RPM 从 settings 读取（启动时固定），未来可通过 admin 端点动态调整

</deferred>

---

*Phase: 7-Protocol Adapters & Streaming*
*Context gathered: 2026-05-19*
