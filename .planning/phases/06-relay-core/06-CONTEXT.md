# Phase 6: Relay Core - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Relay 热路径的核心基础设施：API Key 本地鉴权（Redis 缓存 + DB fallback）、预扣费/结算/退款计费模型（参考 new-api）、路由配置缓存（进程内单例 + version poll）、Call Log 直写 DB（asyncio.create_task fire-and-forget）、Channel 选择器全量移植（weighted round-robin + cooldown + auto-disable + affinity）。

消除 router-service 对 user-service 的所有 HTTP 调用，改为同进程直接调用 service/repository 层。保留 InferenceClient HTTP 调用（到 GPU 服务器的 inference-service）。

不包含：
- 三级速率限制（per-key/per-user/global）— Phase 7
- 协议适配器（OpenAI/Anthropic/Responses 端点）— Phase 7
- SSE 流式响应 — Phase 7
- inference-service HMAC 内部端点 — Phase 8

</domain>

<decisions>
## Implementation Decisions

### API Key 鉴权 + 计费模型（参考 new-api）
- **D-01:** 完整采用 new-api 计费模式：预扣费 + 信任阈值 + 结算差额 + 失败退款
- **D-02:** Redis 缓存策略 — 分离存储：
  - `token:{key_hash}` → JSON{id, user_id, status, expires_at, quota_mode, quota_limit, quota_used, allowed_models, allow_ips, rpm_limit}（60s TTL）
  - `user:quota:{user_id}` → int(balance)，扣费时用 DECRBY 原子操作
- **D-03:** Redis 为余额"热数据"主源，扣费时先 DECRBY Redis，然后 asyncio.create_task 异步写 DB 持久化。DB 作为持久化备份。
- **D-04:** trustQuota 信任阈值 — 固定配置项（settings.TRUST_QUOTA，默认 10 元 = 10,000,000 微分单位）。余额 > trustQuota 时不预扣，直接信任。
- **D-05:** 预扣额度估算 — 基于模型价格：`output_price_per_million × min(max_tokens, 4096) / 1M + input_price_per_million × 2048 / 1M`。模型价格从 RoutingConfigCache model_prices 读取。查不到价格时 fallback 固定 0.1 元。
- **D-06:** Redis 不可用时 fallback DB — token 验证走 DB 查询，余额检查走 DB SELECT，扣费走 DB UPDATE。性能降级但服务不中断。
- **D-07:** token 缓存失效 — 主动失效 + TTL 兜底。admin 禁用/用户删除 key 时主动 DEL token:{key_hash}。正常情况 60s TTL 自然过期。
- **D-08:** 新建 RelayBillingService 封装 Redis 预扣/结算/退款逻辑，内部调用 BalanceService 做 DB 层持久化。BalanceService 保持不变。

### RoutingConfigCache 实现模式
- **D-09:** 进程内单例 + version poll（与 Phase 5 D-06 完全匹配）。每次 relay 请求开始时 GET routing_config:version 比对内存版本号，不一致时 reload DB。
- **D-10:** 缓存数据结构 — 全量 dict，与 router-service ConfigManager.load() 返回格式一致。包含 model_channels、model_prices、user_facing_aliases、tier_model_map、default_user_rpm 等。
- **D-11:** 复用 router-service 的 normalize_runtime_config() 转换逻辑，从 DB routing_settings 表读取原始配置后转换为标准 dict 结构。
- **D-12:** 启动时必须成功加载配置，否则拒绝启动（raise RuntimeError）。与 router-service ConfigManager 行为一致。
- **D-13:** 每 worker 独立缓存。4 个 uvicorn worker 各自维护独立的配置副本，通过 version key 保证最终一致性。内存开销可忽略（配置通常几十 KB）。

### Call Log 直写 DB 生命周期
- **D-14:** 两步写入 — 请求开始时 create_task 写入初始记录（status=pending），请求完成后 create_task 更新记录（status/tokens/cost）+ 调用 RelayBillingService.settle() 结算。
- **D-15:** 独立 session + fire-and-forget — create_task 内获取独立 DB session（不复用请求 session），写入后立即 commit + close。不影响请求主流程。
- **D-16:** 失败处理 — 日志写入失败仅 log warning 不重试；计费结算失败重试（最多 3 次）。计费比日志更重要。
- **D-17:** Call Log update 和计费结算在同一个 create_task 中顺序执行：先写 call_log（tokens/cost/status），然后调用 settle()。

### Channel 选择器移植范围
- **D-18:** 全量移植 ChannelSelector（weighted round-robin + cooldown + auto-disable + health cache + priority-tier descent）+ ChannelAffinityStore + routing.py route_and_resolve() 编排逻辑。
- **D-19:** 保留 InferenceClient HTTP 调用 — inference-service 运行在 GPU 服务器，不可能合并。Phase 6 移植 InferenceClient 代码，保持 HTTP 调用到 settings.INFERENCE_SERVICE_URL。
- **D-20:** 每 worker 独立 ChannelSelector 状态 — cooldown/failure/auto-disable 状态不跨 worker 共享。各 worker 独立发现 channel 故障。与 router-service 单进程行为一致。
- **D-21:** Health check 集成 — 复用 Phase 5 已移植的 HealthCheckService ARQ cron job。ChannelSelector 通过 RoutingConfigCache reload 时获取最新健康状态。
- **D-22:** ChannelAffinityStore 复用 Redis — key = affinity:{user_id}:{model}，value = channel_slug，TTL 300s。多 worker 共享（Redis 天然跨进程）。
- **D-23:** Phase 6 只含 per-account rate limit 检查（channel 选择时排除已达限的 pool_account）。完整三级限流（per-key/per-user/global）属于 Phase 7。

### Claude's Discretion
- ChannelSelector 移植时可调整 threading.Lock 为 asyncio.Lock（单 worker 内无需线程安全，但保留也无害）
- normalize_runtime_config 移植时可根据 api-service 的 DB schema 做适配调整
- RelayBillingService 的具体方法签名和内部组织由 planner 决定
- Redis key 命名前缀（token: / user:quota: / affinity:）可根据项目统一规范微调

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Router-Service 源码（移植源 — 核心逻辑权威参考）
- `services/router-service/src/core/dependencies.py` — require_api_key + TTLCache + init_globals 模式
- `services/router-service/src/gateways/user_identity.py` — ValidatedApiKey dataclass + validate 流程
- `services/router-service/src/services/channel_selector.py` — ChannelSelector 完整实现（155 行）
- `services/router-service/src/services/config_manager.py` — ConfigManager 三级加载 + poll loop
- `services/router-service/src/services/routing.py` — route_and_resolve() 编排逻辑
- `services/router-service/src/services/calllog_buffer.py` — CallLogBuffer（参考但不复用，改为直写）
- `services/router-service/src/gateways/calllog.py` — CallLogGateway create/update 接口
- `services/router-service/src/gateways/calllog_batch.py` — BatchCallLogGateway（将被消除）
- `services/router-service/src/services/channel_affinity.py` — ChannelAffinityStore Redis 实现
- `services/router-service/src/services/upstream.py` — resolve_model_channel_target / normalize_api_base
- `services/router-service/src/utils/runtime_config.py` — normalize_runtime_config() 转换逻辑

### new-api 参考实现（计费模型权威参考）
- `/root/autodl-tmp/new-api-main/service/pre_consume_quota.go` — PreConsumeQuota + trustQuota 信任机制
- `/root/autodl-tmp/new-api-main/service/billing_session.go` — BillingSession Settle/Refund 生命周期
- `/root/autodl-tmp/new-api-main/model/token.go` — GetTokenByKey Redis→DB fallback + ValidateUserToken
- `/root/autodl-tmp/new-api-main/model/user.go` — GetUserQuota Redis→DB fallback
- `/root/autodl-tmp/new-api-main/middleware/auth.go` — TokenAuth 完整鉴权链路

### Phase 4/5 产出（已就绪 — 直接调用）
- `services/api-service/api_service/services/api_key_service.py` — ApiKeyService.validate_by_hash()（DB 层验证）
- `services/api-service/api_service/services/balance_service.py` — BalanceService.consume_for_call_log()（DB 层幂等扣费）
- `services/api-service/api_service/services/admin/routing_setting_service.py` — routing_config:version INCR 已落地
- `services/api-service/api_service/repositories/call_log_repository.py` — CallLogRepository
- `services/api-service/api_service/common/infra/cache.py` — Redis db/2 cache pool + cache_get_or_fetch

### Phase 5 D-06 契约（RoutingConfigCache 消费端）
- Redis key: `routing_config:version`（db/2）
- 写入方: routing_setting_service.update_setting() / batch_update() 末尾 INCR
- 消费方（Phase 6）: 每次请求 GET 比对内存版本号

### Architecture
- `docs/architecture-refactoring.md` — 合并架构方案
- `services/router-service/CLAUDE.md` — router-service 规范（连接池/Gateway/并发安全）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ApiKeyService.validate_by_hash(db, key_hash, model, client_ip)` — DB 层完整验证（Phase 4）
- `BalanceService.consume_for_call_log(db, user_id, request_id, cost, total_tokens, api_key_id)` — DB 层幂等扣费
- `CallLogRepository` — call_log 表 CRUD（Phase 3）
- `get_cache_redis()` — Redis db/2 cache pool（Phase 2）
- `RoutingSettingRepository` — routing_settings 表读取（Phase 3）
- `common/utils/snowflake.py` — Snowflake ID 生成（call_log 主键）
- `common/observability.py` — log_event 结构化日志

### Established Patterns
- Service @staticmethod + `db: AsyncSession` 首参
- asyncio.create_task fire-and-forget（Phase 4 email 已用此模式）
- Redis db/2 用于 cache（mc:* + routing_config:version）
- 配置从 `core.config.settings` 单例读取

### Integration Points
- `api_service/core/lifespan.py` — 注册 RoutingConfigCache 启动/关闭 + ChannelSelector 初始化
- `api_service/core/router.py` — Phase 7 relay 端点将依赖 Phase 6 产出的 dependencies
- Redis db/2 — token 缓存 + user quota + affinity + routing_config:version 共用
- InferenceClient — 需要 httpx.AsyncClient 持久连接池，在 lifespan 初始化

</code_context>

<specifics>
## Specific Ideas

- 参考 new-api 的 trustQuota 机制：余额充足时完全信任不预扣，减少大多数请求的 Redis 写入开销
- Redis quota 用 DECRBY 原子操作保证并发安全，避免 read-modify-write 竞态
- token 缓存不含 balance（balance 单独 key），禁用 key 时只需 DEL token:{key_hash}
- Call Log 两步写入可追踪进行中的请求（status=pending），服务崩溃时可识别未完成请求
- ChannelSelector 的 threading.Lock 在 uvicorn 单 worker 内仍有意义（asyncio 虽然单线程但 Lock 开销极低，保留无害）
- normalize_runtime_config 移植时需要适配：源从 HTTP JSON 响应解析，现改为从 DB RoutingSettingRepository 读取后构造相同结构

</specifics>

<deferred>
## Deferred Ideas

- **完整三级限流（per-key/per-user/global）**：Phase 7 scope，Phase 6 只含 per-account channel 级限流
- **Redis quota 与 DB 的定期对账机制**：如果 Redis 崩溃恢复后余额不一致，需要对账。可在 Phase 9 集成测试时评估是否需要
- **ChannelSelector 状态跨 worker 共享**：当前每 worker 独立，如果发现故障发现延迟不可接受，可改为 Redis 共享。留作 Phase 9 性能验证后决定
- **预扣费额度的动态调整**：当前用固定公式估算，未来可根据历史请求统计动态调整预扣比例

</deferred>

---

*Phase: 6-Relay Core*
*Context gathered: 2026-05-19*
</content>
</invoke>