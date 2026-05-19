---
phase: "07-protocol-adapters-streaming"
plan: "01"
subsystem: relay-infrastructure
tags: [sdk-pool, rate-limiter, backends, protocol, schemas]
dependency_graph:
  requires: [phase-06-relay-core]
  provides: [sdk-client-pool, rate-limiter, upstream-dispatch, protocol-adapters-interface, request-schemas]
  affects: [relay-endpoints, call-lifecycle]
tech_stack:
  added: []
  patterns: [lru-pool, token-bucket, protocol-class, pydantic-v2-schema]
key_files:
  created:
    - services/api-service/api_service/relay/sdk_clients.py
    - services/api-service/api_service/relay/retry_policy.py
    - services/api-service/api_service/relay/rate_limiter.py
    - services/api-service/api_service/relay/lua/token_bucket.lua
    - services/api-service/api_service/relay/backends/__init__.py
    - services/api-service/api_service/relay/backends/openai_backend.py
    - services/api-service/api_service/relay/backends/anthropic_backend.py
    - services/api-service/api_service/relay/upstream_dispatch.py
    - services/api-service/api_service/relay/adapters/__init__.py
    - services/api-service/api_service/relay/adapters/protocol.py
    - services/api-service/api_service/relay/schemas/__init__.py
    - services/api-service/api_service/relay/schemas/chat.py
    - services/api-service/api_service/relay/schemas/anthropic.py
    - services/api-service/api_service/relay/schemas/responses.py
    - services/api-service/tests/relay/__init__.py
    - services/api-service/tests/relay/conftest.py
    - services/api-service/tests/relay/test_rate_limiter.py
    - services/api-service/tests/relay/test_sdk_clients.py
  modified:
    - services/api-service/api_service/relay/dependencies.py
    - services/api-service/api_service/core/lifespan.py
decisions:
  - "ConfigDict(extra='allow') on schemas to support unknown field passthrough"
  - "_build_anthropic_native_params inlined in upstream_dispatch (avoids circular import)"
  - "InMemoryRateLimiter uses TTLCache(maxsize=4096) as Redis fallback"
metrics:
  duration: "12m"
  completed: "2026-05-19"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 14
  tests_passing: 14
  files_created: 18
  files_modified: 2
---

# Phase 7 Plan 01: Relay Infrastructure Layer Summary

SdkClientPool LRU 复用池 + Token Bucket 三级限流 + OpenAI/Anthropic backends + upstream dispatch + ProtocolAdapter/StreamConverter Protocol 定义 + 三协议请求 Schema

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | b532551 | SdkClientPool + retry_policy + backends + dispatch + protocol + schemas |
| 2 | f22f7a1 | RateLimiter 三级限流 + Lua 脚本 + dependencies 扩展 + lifespan 注册 + 测试 |

## Deviations from Plan

None - plan executed exactly as written.

## Key Implementation Details

### SdkClientPool (sdk_clients.py)
- threading.Lock + OrderedDict LRU, max_size parameterized
- get_openai/get_anthropic return cached or new AsyncOpenAI/AsyncAnthropic
- close_all() async closes all pooled clients

### RateLimiter (rate_limiter.py)
- Three-tier check: global -> per-user -> per-key (D-14 order)
- Redis token bucket Lua script for precise rate limiting
- InMemoryRateLimiter fallback (TTLCache, maxsize=4096, ttl=60)
- require_rate_limit FastAPI Depends reads principal from request.state

### Backends + Dispatch
- openai_backend: call_openai with stream/non-stream paths
- anthropic_backend: call_anthropic_native (pass-through) + call_anthropic_from_openai (cross-protocol conversion)
- upstream_dispatch: routes by provider_slug in settings.ANTHROPIC_NATIVE_SLUGS

### Protocol Definitions (adapters/protocol.py)
- ProtocolAdapter: runtime_checkable Protocol with parse_request, format_error, format_non_stream_response, create_stream_converter, get_timeout
- StreamConverter: runtime_checkable Protocol with convert_chunk, get_final_event

### Request Schemas
- ChatCompletionRequest: 512KB content limit, ConfigDict(extra="allow")
- AnthropicMessagesRequest: max_tokens required, 512KB limit
- ResponsesRequest: input as str|list, ConfigDict(extra="allow")

## Self-Check: PASSED
