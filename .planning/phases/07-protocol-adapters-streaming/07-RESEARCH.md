# Phase 7: Protocol Adapters & Streaming - Research

**Researched:** 2026-05-19
**Domain:** LLM Protocol Relay (OpenAI/Anthropic/Responses) + SSE Streaming + Rate Limiting
**Confidence:** HIGH

## Summary

Phase 7 将 router-service 的协议层完整移植到 api-service，构建三个协议端点（OpenAI Chat Completions、Anthropic Messages、OpenAI Responses）的请求处理全链路。核心工作包括：(1) CallLifecycle 编排器拆分移植，(2) SdkClientPool + upstream dispatch 移植，(3) 三个 ProtocolAdapter 实现，(4) SSE 流式响应处理（含 Anthropic 原生透传），(5) 三级 token bucket 限流，(6) GET /v1/models 端点。

Phase 6 已完成所有基础设施（鉴权、计费、路由、日志、Channel 选择），本阶段是在其上构建协议解析和响应格式化层。源码已在 router-service 中完整实现（~2000 行），移植时需适配 api-service 的模块结构和依赖注入模式。

**Primary recommendation:** 按 CONTEXT.md 决策严格移植，重试循环提升到 lifecycle 层，三级限流统一 token bucket Lua 脚本，SdkClientPool 原样移植。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: 保留 CallLifecycle 类作为统一编排器，内部调用 Phase 6 已有模块
- D-02: 拆分到 `relay/lifecycle/` 目录：orchestrator.py、stream.py、finalize.py，每文件 <200 行
- D-03: 重试循环在 lifecycle.execute() 层级，每次重试重新调用 ChannelSelector（排除已失败的）
- D-04: 重试次数从 settings.CHANNEL_MAX_RETRIES 读取（默认 2 次）
- D-05: 原样移植 SdkClientPool（threading.Lock + LRU OrderedDict，max_size=64）
- D-06: SdkClientPool 在 lifespan 初始化，通过 relay/dependencies.py 暴露 get_sdk_client_pool()
- D-07: upstream_dispatch 保持原有路由逻辑：根据 provider_slug 分派到 openai/anthropic 后端
- D-08: SdkClientPool.close_all() 在 lifespan shutdown 时调用
- D-09: 双路径 SSE 设计 — OpenAI 格式流 + Anthropic 原生透传
- D-10: 流迭代逻辑统一在 lifecycle/stream.py，StreamConverter 只负责 chunk 格式转换
- D-11: stream_options.include_usage 默认注入
- D-12: 流式中断处理：client disconnect → 499；上游错误 → 502
- D-13: 三级统一使用 token bucket 算法（单一 Lua 脚本）
- D-14: 检查顺序：global → per-user → per-key
- D-15: per-key RPM 从 token 缓存读取；per-user 从 RoutingConfigCache；global 从 settings
- D-16: InMemory fallback 保留
- D-17: 限流作为 FastAPI Depends 注入
- D-18: 参考 new-api 的 token bucket Lua 脚本实现
- D-19: GET /v1/models 基于用户权限过滤
- D-20: allowed_models 为空时返回全量可用模型

### Claude's Discretion
- ProtocolAdapter 的具体方法签名和内部组织
- Anthropic Messages adapter 的 parse_request 实现细节
- 非流式响应的具体字段清理逻辑
- 429 响应的 Retry-After header 计算方式
- /v1/models 响应中的 model metadata 字段

### Deferred Ideas (OUT OF SCOPE)
- Responses 协议的 background mode
- WebSocket realtime 协议
- per-model 限流
- 限流的动态配置热更新
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RELAY-01 | POST /v1/chat/completions 端点正常工作 | OpenAIChatAdapter + CallLifecycle 编排器 + upstream dispatch |
| RELAY-02 | POST /v1/anthropic/messages 端点正常工作 | AnthropicMessagesAdapter + 原生透传路径 + 跨协议转换 |
| RELAY-03 | POST /v1/responses 端点正常工作 | OpenAIResponsesAdapter + ResponsesStreamConverter |
| RELAY-04 | GET /v1/models 端点返回可用模型列表 | RoutingConfigCache + allowed_models 过滤 |
| RELAY-11 | SSE 流式响应正常工作 | 双路径流式设计 + StreamConverter Protocol + finalize |
| RELAY-12 | 三级速率限制正常工作 | Token bucket Lua + RateLimiter 类 + Depends 注入 |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 请求解析 (parse_request) | API / Backend | — | Pydantic schema 验证 + adapter 格式转换 |
| 速率限制 | API / Backend | Redis (Cache) | Token bucket 算法在 Redis 执行，fallback 在进程内 |
| 上游 SDK 调用 | API / Backend | — | AsyncOpenAI/AsyncAnthropic SDK 直接调用上游 |
| SSE 流式输出 | API / Backend | — | Starlette StreamingResponse + async generator |
| 协议格式转换 | API / Backend | — | StreamConverter 在 Python 层做 chunk 转换 |
| 模型列表过滤 | API / Backend | Redis (Cache) | RoutingConfigCache 提供全量，auth 提供 allowed_models |

## Standard Stack

### Core (已在项目中使用)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openai | >=1.40.0 | OpenAI SDK (AsyncOpenAI) | 官方 SDK，支持流式、重试、超时控制 |
| anthropic | >=0.34.0 | Anthropic SDK (AsyncAnthropic) | 官方 SDK，原生流式事件 |
| fastapi | >=0.115.0 | HTTP 框架 + Depends 注入 | 已在用，限流通过 Depends 注入 |
| starlette | (via FastAPI) | StreamingResponse + SSE | 流式响应的底层实现 |
| redis.asyncio | >=5.0.0 | Token bucket Lua 脚本执行 | 已在用，register_script 注册 Lua |
| cachetools | >=5.0.0 | InMemory fallback 限流 | 已在用，TTLCache |
| pydantic | >=2.5.0 | 请求 schema 验证 | 已在用，v2 性能优异 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| threading | stdlib | SdkClientPool LRU 锁 | 保护 OrderedDict 并发访问 |
| collections.OrderedDict | stdlib | LRU 缓存实现 | SDK client 复用池 |
| json | stdlib | SSE data 序列化 | chunk → JSON string |
| uuid | stdlib | 生成 msg_id/resp_id | Anthropic/Responses 响应格式 |

**Installation:** 无需新增依赖，所有库已在 api-service pyproject.toml 中。[VERIFIED: 项目 pyproject.toml]

## Architecture Patterns

### System Architecture Diagram

```
Client Request
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Router (/v1/chat/completions, /v1/anthropic/    │
│  messages, /v1/responses, /v1/models)                   │
└────────────────────────┬────────────────────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    ▼                    ▼                    ▼
┌────────┐      ┌──────────────┐      ┌────────────┐
│require_│      │require_rate_ │      │ Pydantic   │
│api_key │      │limit (Depends)│      │ Schema     │
│(Phase6)│      │(Phase 7 NEW) │      │ Validation │
└────┬───┘      └──────┬───────┘      └─────┬──────┘
     │                 │                     │
     └─────────────────┼─────────────────────┘
                       ▼
         ┌─────────────────────────┐
         │  ProtocolAdapter        │
         │  .parse_request()       │
         └────────────┬────────────┘
                      ▼
         ┌─────────────────────────┐
         │  CallLifecycle          │
         │  (orchestrator.py)      │
         │  ┌───────────────────┐  │
         │  │ 1. init_call_log  │  │
         │  │ 2. pre_consume    │  │
         │  │ 3. route_resolve  │  │
         │  │ 4. upstream_call  │──┼──► retry loop (D-03)
         │  │    (with retry)   │  │     ├─ dispatch → SdkClientPool
         │  │ 5. build_response │  │     │   ├─ OpenAI backend
         │  └───────────────────┘  │     │   └─ Anthropic backend
         └────────────┬────────────┘     └─ re-select channel on fail
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   ┌─────────────┐       ┌──────────────────┐
   │ Non-stream  │       │ Stream Response   │
   │ JSONResponse│       │ (stream.py)       │
   └─────────────┘       │ ┌──────────────┐  │
                          │ │Path 1: OpenAI│  │
                          │ │ StreamConvert│  │
                          │ ├──────────────┤  │
                          │ │Path 2: Native│  │
                          │ │ Anthropic    │  │
                          │ └──────────────┘  │
                          └────────┬──────────┘
                                   ▼
                          ┌──────────────────┐
                          │ finalize.py      │
                          │ - compute cost   │
                          │ - settle billing │
                          │ - update call_log│
                          └──────────────────┘
```

### Recommended Project Structure
```
services/api-service/api_service/relay/
├── __init__.py
├── auth.py                    # Phase 6 (existing)
├── billing.py                 # Phase 6 (existing)
├── call_log_writer.py         # Phase 6 (existing)
├── channel_affinity.py        # Phase 6 (existing)
├── channel_selector.py        # Phase 6 (existing)
├── config_cache.py            # Phase 6 (existing)
├── dependencies.py            # Phase 6 + Phase 7 additions (get_sdk_client_pool, get_rate_limiter)
├── inference_client.py        # Phase 6 (existing)
├── routing.py                 # Phase 6 (existing)
├── runtime_config.py          # Phase 6 (existing)
├── upstream.py                # Phase 6 (existing)
├── sdk_clients.py             # Phase 7 NEW: SdkClientPool (D-05)
├── rate_limiter.py            # Phase 7 NEW: RateLimiter + InMemoryRateLimiter (D-13~D-18)
├── retry_policy.py            # Phase 7 NEW: should_retry + extract_status_code
├── upstream_dispatch.py       # Phase 7 NEW: dispatch() SDK 路由 (D-07)
├── upstream_caller.py         # Phase 7 NEW: upstream_call_with_retry (D-03)
├── lua/
│   └── token_bucket.lua       # Phase 7 NEW: 统一 token bucket Lua 脚本 (D-13)
├── backends/
│   ├── __init__.py
│   ├── openai_backend.py      # Phase 7 NEW: call_openai (D-07)
│   └── anthropic_backend.py   # Phase 7 NEW: call_anthropic_native/from_openai (D-07)
├── adapters/
│   ├── __init__.py
│   ├── protocol.py            # Phase 7 NEW: ProtocolAdapter + StreamConverter Protocol
│   ├── openai_chat.py         # Phase 7 NEW: OpenAIChatAdapter (RELAY-01)
│   ├── anthropic_messages.py  # Phase 7 NEW: AnthropicMessagesAdapter (RELAY-02)
│   ├── openai_responses.py    # Phase 7 NEW: OpenAIResponsesAdapter (RELAY-03)
│   ├── anthropic_convert.py   # Phase 7 NEW: Anthropic<->OpenAI 转换 + AnthropicStreamConverter
│   └── responses_convert.py   # Phase 7 NEW: Responses<->OpenAI 转换 + ResponsesStreamConverter
├── lifecycle/
│   ├── __init__.py
│   ├── orchestrator.py        # Phase 7 NEW: CallLifecycle.execute() 主编排 (D-01, D-02)
│   ├── stream.py              # Phase 7 NEW: _stream_events + _stream_native_anthropic (D-09, D-10)
│   └── finalize.py            # Phase 7 NEW: _finalize_stream + cost compute (D-02)
└── schemas/
    ├── __init__.py
    ├── chat.py                # Phase 7 NEW: ChatCompletionRequest
    ├── anthropic.py           # Phase 7 NEW: AnthropicMessagesRequest
    └── responses.py           # Phase 7 NEW: ResponsesRequest

services/api-service/api_service/controllers/relay/
├── __init__.py
├── chat.py                    # Phase 7 NEW: POST /v1/chat/completions
├── anthropic.py               # Phase 7 NEW: POST /v1/anthropic/messages
├── responses.py               # Phase 7 NEW: POST /v1/responses
└── models.py                  # Phase 7 NEW: GET /v1/models (RELAY-04)
```

### Pattern 1: CallLifecycle 编排器拆分 (D-02)
**What:** 将 router-service 的 642 行 CallLifecycle 拆分为三个文件
**When to use:** 所有协议端点共享同一编排流程
**Example:**
```python
# relay/lifecycle/orchestrator.py (~180 lines)
# Source: router-service/src/services/call_lifecycle.py (adapted)

class CallLifecycle:
    """Orchestrates the request lifecycle shared by all protocols."""

    def __init__(
        self,
        *,
        adapter: ProtocolAdapter,
        principal: ValidatedApiKey,
        raw_request: Request,
        openai_messages: list[dict],
        forward_payload: dict[str, Any],
        is_stream: bool,
        requested_model: str,
        protocol_context: dict[str, Any],
    ) -> None:
        # ... init fields ...
        self.settings = settings
        self.config_cache = get_routing_config_cache()
        self.channel_selector = get_channel_selector()

    async def execute(self) -> JSONResponse | StreamingResponse:
        """Run full lifecycle with retry at this level (D-03)."""
        await self._init_call_log()
        if error := await self._pre_consume():
            return error
        if error := await self._route():
            return error

        # Inject stream_options for usage tracking (D-11)
        if self.is_stream:
            self.forward_payload.setdefault("stream_options", {"include_usage": True})

        # Retry loop at lifecycle level (D-03)
        max_retries = self.settings.CHANNEL_MAX_RETRIES
        tried_slugs: set[str] = set()
        for attempt in range(max_retries + 1):
            channel_slug = self.target_info.get("channel_slug")
            if channel_slug:
                tried_slugs.add(channel_slug)
            try:
                response = await self._dispatch_upstream()
                if channel_slug:
                    self.channel_selector.report_success(channel_slug)
                break
            except Exception as exc:
                if channel_slug:
                    self.channel_selector.report_failure(channel_slug)
                if attempt < max_retries and should_retry(exc):
                    self.target_info = await self._re_resolve(tried_slugs)
                    continue
                return self._handle_upstream_error(exc)

        if self.is_stream:
            return self._build_stream_response()
        return await self._build_non_stream_response()
```

### Pattern 2: Token Bucket Rate Limiter (D-13, D-14)
**What:** 三级限流统一使用 token bucket，检查顺序 global → per-user → per-key
**When to use:** 所有 relay 端点的前置 Depends
**Example:**
```python
# relay/rate_limiter.py
# Source: router-service/src/services/rate_limiter.py (adapted per D-13~D-18)

class RateLimiter:
    def __init__(self, *, redis: aioredis.Redis | None, settings: ApiServiceSettings):
        self._redis = redis
        self._settings = settings
        self._fallback = InMemoryRateLimiter()
        self._token_bucket_script = None
        if redis is not None:
            lua_path = Path(__file__).parent / "lua" / "token_bucket.lua"
            self._token_bucket_script = redis.register_script(lua_path.read_text())

    async def check_all(
        self, *, user_id: int, key_rpm: int | None, user_rpm: int | None
    ) -> None:
        """Check global → per-user → per-key (D-14). Raises RateLimitExceeded."""
        # 1. Global
        global_rpm = self._settings.RATE_LIMIT_GLOBAL_RPM
        if global_rpm > 0:
            if not await self._check("rl:global", global_rpm):
                raise RateLimitExceeded("Global rate limit exceeded", retry_after=2)
        # 2. Per-user
        effective_user_rpm = user_rpm or self._settings.RATE_LIMIT_DEFAULT_USER_RPM
        if effective_user_rpm > 0:
            if not await self._check(f"rl:user:{user_id}", effective_user_rpm):
                raise RateLimitExceeded(
                    f"Rate limit exceeded: {effective_user_rpm} RPM",
                    retry_after=max(1, 60 // effective_user_rpm),
                )
        # 3. Per-key
        if key_rpm and key_rpm > 0:
            if not await self._check(f"rl:key:{user_id}", key_rpm):
                raise RateLimitExceeded(
                    f"API key rate limit exceeded: {key_rpm} RPM",
                    retry_after=max(1, 60 // key_rpm),
                )

    async def _check(self, key: str, capacity: int) -> bool:
        rate = capacity / 60.0  # tokens per second
        if self._redis and self._token_bucket_script:
            try:
                result = await self._token_bucket_script(
                    keys=[key], args=[str(int(capacity)), str(rate), "1"]
                )
                return int(result) == 1
            except Exception:
                pass
        return self._fallback.check(key, capacity)


# FastAPI Depends (D-17)
async def require_rate_limit(
    principal: ValidatedApiKey = Depends(require_api_key),
) -> None:
    """Rate limit dependency — runs before CallLifecycle."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    limiter = get_rate_limiter()
    await limiter.check_all(
        user_id=principal.user_id,
        key_rpm=principal.user_rpm_limit,  # from token cache
        user_rpm=None,  # uses default from settings
    )
```

### Pattern 3: SSE 流式双路径 (D-09, D-10)
**What:** OpenAI 格式流走 StreamConverter，Anthropic 原生透传直接转发 SDK 事件
**When to use:** 所有流式响应
**Example:**
```python
# relay/lifecycle/stream.py
# Source: router-service/src/services/call_lifecycle.py lines 273-388 (adapted)

async def stream_events(
    lifecycle: "CallLifecycle", converter: StreamConverter | None
) -> AsyncIterator[str]:
    """Standard path: iterate SDK chunks, convert via StreamConverter."""
    collected_content = ""
    stream_usage: dict = {}
    stream_ok = False
    try:
        async for chunk in lifecycle.response:
            chunk_dict = chunk.model_dump(exclude_none=True)
            chunk_dict["model"] = lifecycle.selected_model
            # ... extract usage, content ...
            if converter:
                sse = converter.convert_chunk(chunk_dict)
                if sse:
                    yield sse
            else:
                yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"
        # Final event
        if converter:
            final = converter.get_final_event()
            if final:
                yield final
        else:
            yield "data: [DONE]\n\n"
        stream_ok = True
    except (asyncio.CancelledError, GeneratorExit):
        # D-12: client disconnect → 499
        raise
    except Exception as exc:
        # D-12: upstream error → 502
        pass
    finally:
        await finalize_stream(lifecycle, collected_content, stream_usage, stream_ok, ...)
```

### Pattern 4: Controller 端点 (简洁入口)
**What:** 控制器只负责请求解析和 lifecycle 调用
**When to use:** 每个协议端点
**Example:**
```python
# controllers/relay/chat.py
# Source: router-service/src/controllers/chat.py (identical pattern)

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    adapter = OpenAIChatAdapter()
    messages, payload, ctx = adapter.parse_request(request)
    lifecycle = CallLifecycle(
        adapter=adapter,
        principal=principal,
        raw_request=raw_request,
        openai_messages=messages,
        forward_payload=payload,
        is_stream=request.stream,
        requested_model=str(request.model).strip(),
        protocol_context=ctx,
    )
    return await lifecycle.execute()
```

### Anti-Patterns to Avoid
- **在 adapter 内做 I/O 操作:** adapter 只做格式转换，不调用 DB/Redis/HTTP
- **在 controller 内写重试逻辑:** 重试统一在 lifecycle.execute() 内部（D-03）
- **混用 sliding window 和 token bucket:** 统一 token bucket（D-13）
- **在流式 generator 内 import 模块:** 所有 import 放文件顶部
- **忽略 GeneratorExit:** 必须在 finally 中 finalize（计费结算）

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAI SDK 调用 | 裸 httpx 调用 OpenAI API | openai.AsyncOpenAI SDK | 自动处理 auth header、retry、streaming iterator |
| Anthropic SDK 调用 | 裸 httpx 调用 Anthropic API | anthropic.AsyncAnthropic SDK | 原生事件流、thinking 支持 |
| SSE 格式化 | 手写 HTTP chunked encoding | Starlette StreamingResponse | 自动处理 chunked transfer、connection keep-alive |
| Token bucket 算法 | Python 层面实现 | Redis Lua 脚本 | 原子性、跨进程共享、无竞态 |
| LRU 缓存 | 自己实现 LRU | collections.OrderedDict | 标准库，move_to_end + popitem(last=False) |

**Key insight:** 协议转换逻辑（~800 行）是本阶段唯一需要手写的复杂代码，其余都应复用已有实现。

## Common Pitfalls

### Pitfall 1: 流式中断时计费丢失
**What goes wrong:** client disconnect 触发 GeneratorExit，如果不在 finally 中结算，预扣费永远不退还
**Why it happens:** async generator 被 GC 时 GeneratorExit 可能不触发 finally
**How to avoid:** 使用 asyncio.shield() 保护 finalize 调用（参考源码 line 537-539）
**Warning signs:** 用户余额持续减少但无对应 call_log 记录

### Pitfall 2: stream_options 未注入导致流式无 usage
**What goes wrong:** 流式响应末尾没有 usage chunk，无法计费
**Why it happens:** 某些 OpenAI 兼容 API 默认不返回 usage，需要显式请求
**How to avoid:** D-11 要求在 is_stream=True 时强制注入 `stream_options: {include_usage: true}`
**Warning signs:** 流式请求的 cost 全部为 0

### Pitfall 3: Anthropic 原生透传检测时机
**What goes wrong:** 在 upstream 调用之前就判断 is_native_passthrough，但此时 target_info 可能还没确定
**Why it happens:** 重试可能切换到不同 provider（从 Anthropic 切到 OpenAI 兼容）
**How to avoid:** 在 upstream 调用成功后才设置 is_native_passthrough（参考源码 line 263-265）
**Warning signs:** Anthropic 请求走了 OpenAI 兼容通道但仍尝试原生透传

### Pitfall 4: SdkClientPool 在多 worker 下的内存
**What goes wrong:** 每个 uvicorn worker 独立维护 64 个 client 实例，4 workers = 256 个
**Why it happens:** fork 后每个进程有独立的 pool
**How to avoid:** max_size=64 已经是合理值（每个 client 内存 ~1-2MB），4x64=256 约 256-512MB 在预算内
**Warning signs:** 内存持续增长超过 350MB/worker

### Pitfall 5: Token bucket Lua 脚本的 TIME 精度
**What goes wrong:** Redis TIME 返回秒+微秒，但 token bucket 用秒级精度可能导致突发
**Why it happens:** 如果 rate < 1 token/sec（RPM < 60），秒级精度不够
**How to avoid:** 使用 `now_s = tonumber(now[1]) + tonumber(now[2]) / 1000000` 保留微秒精度（已在源码中实现）
**Warning signs:** 低 RPM 限制（如 5 RPM）时偶尔允许突发

### Pitfall 6: 限流 Depends 与 require_api_key 的执行顺序
**What goes wrong:** 限流检查在鉴权之前执行，导致无效 key 也消耗限流配额
**Why it happens:** FastAPI Depends 按声明顺序执行
**How to avoid:** require_rate_limit 内部依赖 require_api_key 的返回值（principal），确保鉴权先执行
**Warning signs:** 大量 401 请求也触发限流

## Code Examples

### Token Bucket Lua 脚本 (统一版本)
```lua
-- relay/lua/token_bucket.lua
-- Source: router-service/src/services/lua/token_bucket.lua [VERIFIED: 项目源码]
-- KEYS[1] = hash key (fields: tokens, last_refill)
-- ARGV[1] = capacity (max tokens)
-- ARGV[2] = refill_rate (tokens per second)
-- ARGV[3] = cost (tokens to consume, typically 1)
local now = redis.call('TIME')
local now_s = tonumber(now[1]) + tonumber(now[2]) / 1000000
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local last = tonumber(redis.call('HGET', KEYS[1], 'last_refill'))
if not tokens or not last then
    tokens = tonumber(ARGV[1])
    last = now_s
else
    local elapsed = now_s - last
    tokens = math.min(tonumber(ARGV[1]), tokens + elapsed * tonumber(ARGV[2]))
    last = now_s
end
if tokens < tonumber(ARGV[3]) then
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_refill', last)
    redis.call('EXPIRE', KEYS[1], 120)
    return 0
end
tokens = tokens - tonumber(ARGV[3])
redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_refill', last)
redis.call('EXPIRE', KEYS[1], 120)
return 1
```

### GET /v1/models 端点 (D-19, D-20)
```python
# controllers/relay/models.py
# Source: CONTEXT.md D-19/D-20 requirements

@router.get("/v1/models")
async def list_models(
    principal: ValidatedApiKey = Depends(require_api_key),
):
    """Return available models filtered by API key permissions."""
    config_cache = get_routing_config_cache()
    config = config_cache.load()

    # All user-facing models from config
    all_models = set(config.get("user_facing_aliases", []))

    # Filter by allowed_models if set (D-20: empty = no restriction)
    allowed = principal.allowed_models
    if allowed:
        allowed_set = set(m.strip() for m in allowed.split(",") if m.strip())
        available = all_models & allowed_set
    else:
        available = all_models

    # Format as OpenAI model list
    models = [
        {
            "id": model_id,
            "object": "model",
            "created": 0,
            "owned_by": "eucal-ai",
        }
        for model_id in sorted(available)
    ]
    return {"object": "list", "data": models}
```

### SdkClientPool (D-05, 原样移植)
```python
# relay/sdk_clients.py
# Source: router-service/src/services/sdk_clients.py [VERIFIED: 项目源码]

class SdkClientPool:
    """LRU-bounded pool of SDK client instances keyed by (base_url, api_key)."""

    def __init__(self, max_size: int = 64) -> None:
        self._max_size = max_size
        self._openai_clients: OrderedDict[tuple[str, str], AsyncOpenAI] = OrderedDict()
        self._anthropic_clients: OrderedDict[tuple[str, str], AsyncAnthropic] = OrderedDict()
        self._lock = threading.Lock()

    def get_openai(self, base_url: str, api_key: str) -> AsyncOpenAI:
        key = (base_url, api_key)
        with self._lock:
            if key in self._openai_clients:
                self._openai_clients.move_to_end(key)
                return self._openai_clients[key]
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            self._openai_clients[key] = client
            if len(self._openai_clients) > self._max_size:
                self._openai_clients.popitem(last=False)
            return client
    # ... get_anthropic, close_all similar ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| litellm.acompletion 统一调用 | 直接 openai/anthropic SDK | Phase 7 设计决策 | 去除 litellm 50MB 依赖，完全控制流式行为 |
| 重试在 upstream_caller 内部 | 重试在 lifecycle.execute() 层 | D-03 | 每次重试可重新选择 channel |
| sliding_window + token_bucket 混用 | 统一 token_bucket | D-13 | 简化维护，一个 Lua 脚本覆盖所有场景 |
| HTTP 代理到 user-service 验证 | 本地 DB + Redis 三级缓存 | Phase 6 | 消除跨服务延迟 |

**Deprecated/outdated:**
- litellm: 已移除，直接使用官方 SDK [VERIFIED: CLAUDE.md "What NOT to Use"]
- sliding_window.lua: 不再使用，统一 token_bucket（D-13）

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | openai SDK AsyncOpenAI.chat.completions.create(stream=True) 返回 async iterator | Code Examples | 如果 API 变更需要调整 stream 消费方式 |
| A2 | anthropic SDK AsyncAnthropic.messages.create(stream=True) 返回原生事件流 | Code Examples | 如果 SDK 版本变更事件格式 |
| A3 | Redis register_script 在 redis.asyncio 5.x 中支持 Lua 脚本注册 | Standard Stack | 如果 API 不同需要调整注册方式 |

**Note:** A1-A3 均基于项目中已运行的 router-service 代码验证，风险极低。

## Open Questions

1. **per-key 限流的 key 格式**
   - What we know: D-14 说检查顺序是 global → per-user → per-key
   - What's unclear: per-key 的 Redis key 用 key_hash 还是 api_key_id？
   - Recommendation: 用 `rl:key:{api_key_id}` — 数字 ID 更短，且 key_hash 是 64 字符 SHA256

2. **CallLifecycle 拆分后的 self 引用**
   - What we know: D-02 要求拆分为 orchestrator/stream/finalize 三个文件
   - What's unclear: stream.py 和 finalize.py 是独立函数还是 CallLifecycle 的方法？
   - Recommendation: 作为独立 async 函数，接收 lifecycle 实例作为参数（避免循环 import）

3. **register_relay_resources 是否需要扩展**
   - What we know: Phase 6 已定义 register_relay_resources 但未在 main.py 调用
   - What's unclear: Phase 7 是否应该在同一函数中添加 SdkClientPool 和 RateLimiter 初始化
   - Recommendation: 扩展 register_relay_resources 添加 sdk_client_pool 和 rate_limiter，在 main.py 中调用

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 0.24 |
| Config file | services/api-service/pytest.ini (or pyproject.toml [tool.pytest]) |
| Quick run command | `cd services/api-service && python -m pytest tests/ -x -q --timeout=30` |
| Full suite command | `cd services/api-service && python -m pytest tests/ --timeout=60` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RELAY-01 | Chat completions endpoint works | integration | `pytest tests/relay/test_chat_endpoint.py -x` | Wave 0 |
| RELAY-02 | Anthropic messages endpoint works | integration | `pytest tests/relay/test_anthropic_endpoint.py -x` | Wave 0 |
| RELAY-03 | Responses endpoint works | integration | `pytest tests/relay/test_responses_endpoint.py -x` | Wave 0 |
| RELAY-04 | Models list endpoint works | unit | `pytest tests/relay/test_models_endpoint.py -x` | Wave 0 |
| RELAY-11 | SSE streaming works | integration | `pytest tests/relay/test_streaming.py -x` | Wave 0 |
| RELAY-12 | Three-tier rate limiting works | unit | `pytest tests/relay/test_rate_limiter.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/relay/ -x -q --timeout=30`
- **Per wave merge:** `pytest tests/ --timeout=60`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/relay/test_rate_limiter.py` — covers RELAY-12 (token bucket + fallback)
- [ ] `tests/relay/test_chat_endpoint.py` — covers RELAY-01 (mock upstream)
- [ ] `tests/relay/test_anthropic_endpoint.py` — covers RELAY-02
- [ ] `tests/relay/test_responses_endpoint.py` — covers RELAY-03
- [ ] `tests/relay/test_models_endpoint.py` — covers RELAY-04
- [ ] `tests/relay/test_streaming.py` — covers RELAY-11 (SSE format validation)
- [ ] `tests/relay/conftest.py` — shared fixtures (mock SdkClientPool, mock Redis)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | require_api_key Depends (Phase 6, already implemented) |
| V3 Session Management | no | Relay uses stateless API key auth, no sessions |
| V4 Access Control | yes | allowed_models filtering on /v1/models; per-key RPM |
| V5 Input Validation | yes | Pydantic schema validation (max 512KB content, max 256 messages) |
| V6 Cryptography | no | No crypto in this phase (key hashing is Phase 6) |

### Known Threat Patterns for Protocol Relay

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF via upstream URL | Tampering | _validate_upstream_url() blocks private networks (already in upstream.py) |
| Rate limit bypass via key rotation | Denial of Service | per-user limit catches this (D-14 checks user level too) |
| Streaming response injection | Information Disclosure | SSE format enforced by StreamConverter, no raw user content in event type |
| Upstream API key exposure in error | Information Disclosure | sanitize_error() strips sensitive data from error messages |
| Resource exhaustion via large requests | Denial of Service | Pydantic 512KB content limit + 256 message limit |

## Sources

### Primary (HIGH confidence)
- router-service/src/services/call_lifecycle.py — 完整 CallLifecycle 实现 (642 行)
- router-service/src/services/rate_limiter.py — RateLimiter 三级限流 (134 行)
- router-service/src/services/sdk_clients.py — SdkClientPool LRU (53 行)
- router-service/src/services/upstream_dispatch.py — SDK 路由分派 (47 行)
- router-service/src/services/upstream_caller.py — 重试逻辑 (98 行)
- router-service/src/services/adapters/ — 三个 ProtocolAdapter 实现
- router-service/src/services/anthropic_convert.py — Anthropic 转换 + StreamConverter (542 行)
- router-service/src/services/responses_convert.py — Responses 转换 + StreamConverter (488 行)
- router-service/src/services/lua/token_bucket.lua — Lua 脚本 (27 行)
- new-api-main/common/limiter/lua/rate_limit.lua — 参考 token bucket 实现

### Secondary (MEDIUM confidence)
- api-service/relay/dependencies.py — Phase 6 已有的单例管理模式
- api-service/core/lifespan.py — LifespanRegistry 注册模式
- api-service/core/config.py — 已有的 RATE_LIMIT_* / SDK_CLIENT_POOL_* 配置

### Tertiary (LOW confidence)
- None — 所有关键实现均有项目内源码验证

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - 所有库已在项目中使用，无新增依赖
- Architecture: HIGH - 完整源码可参考，移植而非新建
- Pitfalls: HIGH - 基于已运行的 router-service 生产经验

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (稳定移植，无外部依赖变更风险)
