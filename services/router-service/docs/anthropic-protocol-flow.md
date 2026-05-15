# Anthropic 协议转换流程

## 整体架构

```
Client (Claude Code / Anthropic SDK)
    │
    │  POST /v1/anthropic/messages
    │  Headers: x-api-key, anthropic-version
    │  Body: Anthropic Messages 格式
    │
    ▼
┌─────────────────────────────────────────────┐
│           Router Service (8003)              │
│                                             │
│  1. 鉴权 (require_api_key)                  │
│  2. Pydantic 校验 (AnthropicMessagesRequest) │
│  3. Anthropic → OpenAI 格式转换              │
│  4. 智能路由 (route_and_resolve)             │
│  5. litellm.acompletion (OpenAI 格式)       │
│  6. OpenAI → Anthropic 格式转换              │
│  7. 返回 Anthropic Messages 响应             │
└─────────────────────────────────────────────┘
    │
    │  litellm.acompletion(
    │    model="openai/xxx",
    │    custom_llm_provider="openai",
    │    api_base="https://upstream.com/v1",
    │    messages=[OpenAI格式],
    │    **forward_payload
    │  )
    │
    ▼
┌─────────────────────────┐
│   Upstream (OpenAI 兼容)  │
│   - OpenRouter           │
│   - StepFun              │
│   - 其他 OpenAI 兼容 API  │
└─────────────────────────┘
```

## 请求转换：Anthropic → OpenAI

### 入口
`services/anthropic_convert.py` → `anthropic_to_openai_request(request)`

### 字段映射

| Anthropic 请求字段 | OpenAI 转换结果 | 说明 |
|---|---|---|
| `model` | 不进入 payload，由路由层决定 | 路由后用 `selected_model` |
| `messages` | `messages` (格式转换) | 见下方详细映射 |
| `system` (str) | `{"role":"system","content":"..."}` | 插入 messages 头部 |
| `system` (list) | 合并 text blocks → system message | `cache_control` 丢失 |
| `max_tokens` | `forward_payload["max_tokens"]` | 直接映射 |
| `temperature` | `forward_payload["temperature"]` | 直接映射 |
| `top_p` | `forward_payload["top_p"]` | 直接映射 |
| `top_k` | `forward_payload["top_k"]` | 直接映射，OpenAI 不支持但 litellm 可能透传 |
| `stop_sequences` | `forward_payload["stop"]` | 字段名不同 |
| `stream` | 控制流式/非流式调用 | 不进入 payload |
| `tools` | `forward_payload["tools"]` (格式转换) | 见下方 |
| `tool_choice` | `forward_payload["tool_choice"]` | auto→"auto", any→"required", tool→指定 |
| `metadata.user_id` | `forward_payload["user"]` | OpenAI 的 user 字段 |
| `thinking` | **不转发** | OpenAI 不支持，转发会导致 litellm 报错 |

### Messages 内容块映射

| Anthropic content block | OpenAI 格式 |
|---|---|
| `{"type":"text","text":"..."}` | `{"type":"text","text":"..."}` 或纯字符串 |
| `{"type":"image","source":{"type":"base64",...}}` | `{"type":"image_url","image_url":{"url":"data:mime;base64,..."}}` |
| `{"type":"image","source":{"type":"url",...}}` | `{"type":"image_url","image_url":{"url":"..."}}` |
| `{"type":"tool_use","id":"...","name":"...","input":{}}` | `tool_calls: [{"id":"...","type":"function","function":{"name":"...","arguments":"..."}}]` |
| `{"type":"tool_result","tool_use_id":"...","content":"..."}` | `{"role":"tool","tool_call_id":"...","content":"..."}` |
| `tool_result.is_error = true` | content 前加 `[TOOL_ERROR]` 前缀 |

### Tools 转换

```
Anthropic:                          OpenAI:
{                                   {
  "name": "get_weather",              "type": "function",
  "description": "...",               "function": {
  "input_schema": {                     "name": "get_weather",
    "type": "object",                   "description": "...",
    "properties": {...}                 "parameters": {
  }                                       "type": "object",
}                                         "properties": {...}
                                        }
                                      }
                                    }
```

### 丢失的字段（无 OpenAI 等价物）

| 字段 | 处理方式 |
|---|---|
| `thinking` | Schema 接收但不转发（转发会导致 litellm UnsupportedParamsError） |
| `cache_control` (system/content/tools 上) | 丢失，OpenAI 无此概念 |
| `tool_choice.disable_parallel_tool_use` | 丢失 |
| `service_tier` | 丢失 |

---

## 响应转换：OpenAI → Anthropic

### 非流式
`services/anthropic_convert.py` → `openai_to_anthropic_response(openai_resp, selected_model)`

### 字段映射

| OpenAI 响应字段 | Anthropic 响应字段 |
|---|---|
| `id` | 重新生成 `msg_{uuid}` |
| — | `type: "message"` (固定) |
| `choices[0].message.role` | `role: "assistant"` (固定) |
| `model` | `model` (用路由后的 selected_model) |
| `choices[0].message.content` | `content: [{"type":"text","text":"..."}]` |
| `choices[0].message.content` 含 `<think>` | 拆分为 `[{"type":"thinking","thinking":"..."},{"type":"text","text":"..."}]` |
| `choices[0].message.tool_calls` | `content: [{"type":"tool_use","id":"...","name":"...","input":{}}]` |
| `choices[0].finish_reason` | `stop_reason` (映射见下) |
| `usage.prompt_tokens` | `usage.input_tokens` |
| `usage.completion_tokens` | `usage.output_tokens` |
| — | `usage.cache_creation_input_tokens: 0` |
| — | `usage.cache_read_input_tokens: 0` |
| — | `stop_sequence: null` |

### Stop Reason 映射

| OpenAI `finish_reason` | Anthropic `stop_reason` |
|---|---|
| `stop` | `end_turn` |
| `length` | `max_tokens` |
| `max_tokens` | `max_tokens` |
| `tool_calls` | `tool_use` |
| `content_filter` | `end_turn` |

### Thinking 处理（`<think>` 标签）

上游 OpenAI 兼容模型可能在 content 中返回 `<think>...</think>` 标签：

```
输入: "<think>Let me reason about this</think>The answer is 42"

输出:
content: [
  {"type": "thinking", "thinking": "Let me reason about this"},
  {"type": "text", "text": "The answer is 42"}
]
```

---

## 流式转换：OpenAI SSE → Anthropic SSE

### 类
`services/anthropic_convert.py` → `AnthropicStreamConverter`

### 事件序列

```
OpenAI 流式 chunk                    Anthropic SSE 事件
─────────────────                    ─────────────────
(首个 chunk)                    →    event: message_start
                                     event: ping

delta.content = "Hello"         →    event: content_block_start (type: text)
                                     event: content_block_delta (text_delta)

delta.content = " world"        →    event: content_block_delta (text_delta)

delta.content = "<think>..."    →    event: content_block_start (type: thinking)
                                     event: content_block_delta (thinking_delta)

delta.content = "</think>..."   →    event: content_block_stop
                                     event: content_block_start (type: text)
                                     event: content_block_delta (text_delta)

delta.tool_calls[0] (new)       →    event: content_block_stop (关闭 text)
                                     event: content_block_start (type: tool_use)

delta.tool_calls[0].args        →    event: content_block_delta (input_json_delta)

finish_reason = "stop"          →    event: content_block_stop
                                     event: message_delta (stop_reason)
                                     event: message_stop
```

### Think 标签状态机

流式中 `<think>` 标签可能跨多个 chunk 到达，使用状态机处理：

```
状态: idle → thinking → done

idle:     缓冲文本，检测 "<think>"
          - 找到 → 发 thinking block start，转入 thinking
          - 缓冲超过 7 字符无匹配 → flush 为普通 text

thinking: 直接发 thinking_delta
          - 检测到 "</think>" → 发 block stop，转入 done

done:     所有后续文本作为普通 text 发出
```

---

## 错误格式

所有错误返回 Anthropic 标准格式：

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "invalid api key"
  }
}
```

| HTTP 状态码 | error.type |
|---|---|
| 400 | `invalid_request_error` |
| 401 | `authentication_error` |
| 403 | `permission_error` |
| 404 | `not_found_error` |
| 422 | `invalid_request_error` |
| 429 | `rate_limit_error` |
| 500 | `api_error` |
| 502/503 | `overloaded_error` |

---

## 当前已知限制

1. **`thinking` 不转发**：因为上游是 OpenAI 兼容端点，不支持 Anthropic 的 thinking 参数。如果转发，litellm 会抛出 `UnsupportedParamsError`。
2. **`cache_control` 丢失**：OpenAI 协议无等价物。
3. **模型名问题**：Claude Code 客户端可能在本地校验模型名是否匹配 `claude-*` 模式，导致 `"auto"` 被拒绝（请求不会发到服务器）。需要在 ccswitch 中配置 Claude 官方模型名，并在 router 的 `user_facing_aliases` 中添加对应映射。
4. **响应 model 字段**：返回的是路由后的实际模型名（如 `step-3.5-flash`），而非请求的 `auto`。某些客户端可能期望返回请求时的模型名。

---

## 文件清单

| 文件 | 职责 |
|---|---|
| `src/schemas/anthropic.py` | Pydantic 请求 schema |
| `src/services/anthropic_convert.py` | 双向格式转换（请求+响应+流式） |
| `src/controllers/messages.py` | 端点控制器，编排整个流程 |
| `src/common/core/exception_handlers.py` | 全局错误格式化（Anthropic 路径感知） |
