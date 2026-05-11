# 多协议兼容层文档

router-service 作为 API 网关，支持三种协议格式。所有协议最终统一转换为 OpenAI Chat Completions 格式调用上游 LLM（通过 litellm）。

## 支持的协议端点

| 端点 | 协议 | 适用客户端 |
|------|------|-----------|
| `POST /v1/chat/completions` | OpenAI Chat Completions | ChatGPT 兼容客户端、各类 SDK |
| `POST /v1/anthropic/messages` | Anthropic Messages API | Claude Code CLI、Anthropic SDK |
| `POST /v1/responses` | OpenAI Responses API | Codex CLI、OpenAI Agents SDK |

## 架构概览

```
客户端请求 (任意协议)
    │
    ▼
┌─────────────────────────────┐
│  controllers/chat.py        │  ← OpenAI Chat Completions (直通)
│  controllers/messages.py    │  ← Anthropic → OpenAI 转换
│  controllers/responses.py   │  ← Responses → OpenAI 转换
└─────────────────────────────┘
    │
    ▼  统一的 OpenAI Chat Completions 格式
┌─────────────────────────────┐
│  route_and_resolve()        │  智能路由 + 模型选择
│  upstream_call_with_retry() │  上游调用 (litellm)
└─────────────────────────────┘
    │
    ▼  OpenAI Chat Completions 响应
┌─────────────────────────────┐
│  anthropic_convert.py       │  ← OpenAI → Anthropic 响应转换
│  responses_convert.py       │  ← OpenAI → Responses 响应转换
└─────────────────────────────┘
    │
    ▼
客户端响应 (对应协议格式)
```

---

## Anthropic Messages API (`/v1/anthropic/messages`)

### 请求格式

```json
{
  "model": "auto",
  "max_tokens": 1024,
  "system": "You are a helpful assistant.",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

### 转换逻辑 (`services/anthropic_convert.py`)

**请求转换 (Anthropic → OpenAI):**
- `system` → OpenAI system message
- `messages[].content` 支持 text、image (base64/url)、tool_use、tool_result
- `tools` → OpenAI function tools 格式 (`input_schema` → `parameters`)
- `tool_choice` 映射: `auto`→`auto`, `any`→`required`, `tool`→`{type:function, function:{name}}`

**响应转换 (OpenAI → Anthropic):**
- `choices[0].message.content` → `content[{type:"text", text:"..."}]`
- `choices[0].message.tool_calls` → `content[{type:"tool_use", id, name, input}]`
- `finish_reason` 映射: `stop`→`end_turn`, `length`→`max_tokens`, `tool_calls`→`tool_use`

**流式转换 (`AnthropicStreamConverter`):**
```
OpenAI chunk (delta.content)     → content_block_delta (text_delta)
OpenAI chunk (delta.tool_calls)  → content_block_delta (input_json_delta)
OpenAI chunk (finish_reason)     → message_delta + message_stop
```

SSE 事件序列:
```
event: message_start
event: content_block_start
event: content_block_delta  (重复多次)
event: content_block_stop
event: message_delta
event: message_stop
```

### 错误格式

```json
{"type": "error", "error": {"type": "invalid_request_error", "message": "..."}}
```

### 测试

```bash
curl -X POST http://localhost:8003/v1/anthropic/messages \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "auto",
    "max_tokens": 200,
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

---

## OpenAI Responses API (`/v1/responses`)

### 请求格式

```json
{
  "model": "auto",
  "instructions": "You are a coding assistant.",
  "input": [
    {"role": "user", "content": "Write a hello world in Python"}
  ],
  "max_output_tokens": 1000,
  "stream": true,
  "tools": [
    {
      "type": "function",
      "name": "exec_command",
      "description": "Execute a shell command",
      "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
    }
  ],
  "tool_choice": "auto"
}
```

`input` 支持:
- 字符串: 直接作为 user message
- 数组: 支持 role-based messages、`function_call`、`function_call_output`

### 转换逻辑 (`services/responses_convert.py`)

**请求转换 (Responses → OpenAI):**
- `instructions` → system message
- `input` (string) → user message
- `input` (array):
  - `{role: "user/assistant/system/developer"}` → 对应 OpenAI message
  - `{type: "function_call"}` → assistant message with tool_calls
  - `{type: "function_call_output"}` → tool message
- `tools` 格式转换: `{type, name, description, parameters}` → `{type, function: {name, description, parameters}}`
- `max_output_tokens` → `max_tokens`

**响应转换 (OpenAI → Responses):**
- `choices[0].message.content` → `output[{type:"message", content:[{type:"output_text", text}]}]`
- `choices[0].message.tool_calls` → `output[{type:"function_call", call_id, name, arguments}]`

**流式转换 (`ResponsesStreamConverter`):**

SSE 事件序列:
```
event: response.created
event: response.output_item.added        (message item)
event: response.content_part.added
event: response.output_text.delta        (重复多次)
event: response.output_text.done
event: response.content_part.done
event: response.output_item.done
event: response.output_item.added        (function_call item, 如有工具调用)
event: response.function_call_arguments.delta  (重复多次)
event: response.function_call_arguments.done
event: response.output_item.done
event: response.completed                (包含完整 response 对象和 usage)
```

关键设计:
- `response.completed` 延迟发送，等待上游 usage chunk 到达后再发，确保 token 统计准确
- 流中途出错时仍发送 `response.completed`，避免客户端报 "stream closed before response.completed"
- `finish_reason: "length"` 时 response status 设为 `"incomplete"`，附带 `incomplete_details`
- 上游连接失败时 streaming 模式返回 SSE 格式错误（而非 JSON 502）

### 错误格式

HTTP 错误码 + JSON body:
```json
{"detail": "upstream service error"}
```

### 测试

```bash
# 基础文本
curl -X POST http://localhost:8003/v1/responses \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","input":"Say hello","max_output_tokens":100,"stream":true}'

# 工具调用
curl -X POST http://localhost:8003/v1/responses \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"auto",
    "input":[{"role":"user","content":"List files in current dir"}],
    "max_output_tokens":500,
    "stream":true,
    "tools":[{"type":"function","name":"exec_command","description":"Run a command","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}],
    "tool_choice":"auto"
  }'

# 多轮对话 (含工具结果)
curl -X POST http://localhost:8003/v1/responses \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"auto",
    "input":[
      {"role":"user","content":"What files are here?"},
      {"type":"function_call","call_id":"call_123","name":"exec_command","arguments":"{\"command\":\"ls\"}"},
      {"type":"function_call_output","call_id":"call_123","output":"file1.py\nfile2.py"},
      {"role":"user","content":"Now show me file1.py"}
    ],
    "max_output_tokens":500,
    "stream":true
  }'
```

---

## 相关源文件

| 文件 | 职责 |
|------|------|
| `schemas/anthropic.py` | Anthropic 请求 Pydantic 模型 |
| `schemas/responses.py` | Responses 请求 Pydantic 模型 |
| `services/anthropic_convert.py` | Anthropic ↔ OpenAI 格式转换 + 流式状态机 |
| `services/responses_convert.py` | Responses ↔ OpenAI 格式转换 + 流式状态机 |
| `controllers/messages.py` | `/v1/anthropic/messages` 端点处理 |
| `controllers/responses.py` | `/v1/responses` 端点处理 |
| `controllers/chat.py` | `/v1/chat/completions` 端点处理 (直通) |
