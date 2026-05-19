---
phase: "07-protocol-adapters-streaming"
plan: "02"
subsystem: relay-lifecycle-adapters
tags: [call-lifecycle, protocol-adapters, streaming, sse, relay-endpoints]
dependency_graph:
  requires: [07-01-relay-infrastructure]
  provides: [call-lifecycle-orchestrator, protocol-adapters, relay-endpoints, sse-streaming]
  affects: [relay-hot-path, billing-settlement, upstream-dispatch]
tech_stack:
  added: []
  patterns: [lifecycle-orchestrator, protocol-adapter, dual-stream-path, fire-and-forget-finalize]
key_files:
  created:
    - services/api-service/api_service/relay/lifecycle/__init__.py
    - services/api-service/api_service/relay/lifecycle/orchestrator.py
    - services/api-service/api_service/relay/lifecycle/stream.py
    - services/api-service/api_service/relay/lifecycle/finalize.py
    - services/api-service/api_service/relay/adapters/openai_chat.py
    - services/api-service/api_service/relay/adapters/anthropic_messages.py
    - services/api-service/api_service/relay/adapters/anthropic_convert.py
    - services/api-service/api_service/relay/adapters/openai_responses.py
    - services/api-service/api_service/relay/adapters/responses_convert.py
    - services/api-service/api_service/controllers/relay/__init__.py
    - services/api-service/api_service/controllers/relay/chat.py
    - services/api-service/api_service/controllers/relay/anthropic.py
    - services/api-service/api_service/controllers/relay/responses.py
    - services/api-service/api_service/controllers/relay/models.py
  modified:
    - services/api-service/api_service/main.py
decisions:
  - "Lifecycle split into 3 files (orchestrator/stream/finalize) for maintainability"
  - "Orchestrator at 211 lines (slightly over 200 target) to keep all orchestration logic cohesive"
  - "Adapters use wrapper classes for StreamConverter protocol compliance"
  - "Relay routes mounted at app root (not /api/v1) for SDK compatibility"
metrics:
  duration: "18m"
  completed: "2026-05-19"
  tasks_completed: 2
  tasks_total: 2
  files_created: 14
  files_modified: 1
---

# Phase 7 Plan 02: CallLifecycle + Protocol Adapters + Relay Endpoints Summary

CallLifecycle orchestrator with retry loop, 3 protocol adapters (OpenAI Chat/Anthropic Messages/OpenAI Responses), dual-path SSE streaming, finalize with asyncio.shield, and 4 relay endpoints mounted at app root

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 189a610 | CallLifecycle orchestrator + 3 protocol adapters + stream/finalize |
| 2 | d98e9dc | 4 relay endpoint controllers + route mounting |

## Deviations from Plan

None - plan executed exactly as written.

## Key Implementation Details

### CallLifecycle (lifecycle/orchestrator.py)
- execute() orchestrates: init_call_log -> check_balance -> route -> call_upstream -> response
- Retry loop uses settings.CHANNEL_MAX_RETRIES with channel re-resolution on failure
- Reports success/failure to ChannelSelector for circuit-breaker behavior
- Detects native Anthropic pass-through after upstream resolves (provider_slug in ANTHROPIC_NATIVE_SLUGS)

### Streaming (lifecycle/stream.py)
- stream_events(): Standard path — iterates OpenAI SDK chunks, applies optional StreamConverter
- stream_native_anthropic(): Anthropic pass-through — preserves original event types (message_start, content_block_delta, etc.)
- Both share try/except/finally pattern with finalize_stream in finally block

### Finalize (lifecycle/finalize.py)
- Computes final_status (200/499/502) based on stream outcome
- Calculates actual cost from model_prices config
- Uses asyncio.shield for client_cancelled to protect billing writes from cancellation
- Delegates to update_call_log_and_settle (fire-and-forget)

### OpenAIChatAdapter
- protocol_name = "chat", no stream converter needed (native format)
- Strips think tags, reasoning_content, provider_specific_fields from responses

### AnthropicMessagesAdapter
- protocol_name = "messages", uses anthropic_to_openai_request for cross-protocol conversion
- AnthropicStreamConverter handles think-tag state machine for streaming
- Native pass-through path returns None converter (raw SDK events streamed directly)

### OpenAIResponsesAdapter
- protocol_name = "responses", converts to/from OpenAI chat format
- ResponsesStreamConverter emits response.created, output_item.added, text.delta, completed events
- Supports function_call streaming with proper output_index tracking

### Relay Endpoints
- POST /v1/chat/completions — OpenAI Chat protocol
- POST /v1/anthropic/messages + /v1/anthropic/v1/messages — Anthropic Messages (dual path)
- POST /v1/responses — OpenAI Responses protocol
- GET /v1/models — Model listing with allowed_models filtering (D-19, D-20)
- All mounted at app root (not /api/v1) for SDK client compatibility

## Self-Check: PASSED
