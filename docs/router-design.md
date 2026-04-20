# router-service 设计文档

## 概述

将 `eucalAI_backend/demo_5.py`（~2600 行单文件）拆解为标准 FastAPI 服务，同步落地 v3 改动。使用 uv 管理依赖。

完成后 `demo_5.py` 不再保留，由本服务完全替代。

## 项目结构

```
router-service/
├── pyproject.toml
├── runtime_config.json          # 运行时热加载配置（tier/模型/权重/provider）
├── model_paths.json             # 模型文件路径配置（Qwen backbone、5 路 CG-TabM、proto artifact）
├── src/
│   └── router_service/
│       ├── __init__.py
│       ├── main.py              # FastAPI app 创建 + uvicorn 入口 + CLI
│       ├── config.py            # 加载 model_paths.json；静态常量（HEADS、NORMALIZE_RANGES、PROTO 映射）
│       ├── deps.py              # FastAPI 依赖注入（API key 校验、全局单例）
│       ├── schemas.py           # Pydantic 请求/响应模型
│       ├── logging.py           # 统一 logging 配置 + 路由决策日志记录器
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── chat.py          # POST /v1/chat/completions
│       │   ├── completions.py   # POST /v1/completions
│       │   └── meta.py          # GET /ready, /v1/models, /v1/router/config
│       ├── services/
│       │   ├── __init__.py
│       │   ├── router_engine.py # HybridIntegratedDifficultyRouter
│       │   └── upstream.py      # litellm 上游调用 + resolve_model_provider_target
│       ├── nn/
│       │   ├── __init__.py
│       │   ├── cg_tabm.py      # CGTabMRegressor、BatchEnsembleMLP、HardConcreteGates 等
│       │   └── probe.py        # RegressionNN、load_probe_bundle
│       └── utils/
│           ├── __init__.py
│           ├── text.py          # 文本处理（truncate、stringify、normalize）
│           ├── scoring.py       # 分数归一化、band 解析、tier 映射、加权计算
│           ├── runtime_config.py # RuntimeConfigStore + 配置校验/归一化
│           └── input_builder.py # 路由输入构建（shared_record、canonical text、full llm input）
├── cli.py                       # 离线批量跑目录 + 单条记录模式
└── logs/                        # 运行时日志输出目录
```

## 配置文件设计

### model_paths.json — 模型文件路径（启动时加载，不热更新）

```json
{
  "qwen_backbone": "/root/autodl-tmp/models/Qwen/Qwen2.5-7B-Instruct",
  "routers": {
    "swe": {
      "model": "/root/autodl-tmp/纠错/para/best_cg_tabm_router_swe.pth",
      "scaler": "/root/autodl-tmp/纠错/para/cg_tabm_robust_scaler_swe.pkl"
    },
    "tool": {
      "model": "/root/autodl-tmp/工具调用/API-Bank/新路由方法_apibank/final_results/saved_models/best_cg_tabm_from_final_tsv.pth",
      "scaler": "/root/autodl-tmp/工具调用/API-Bank/新路由方法_apibank/final_results/saved_models/best_cg_tabm_scaler_from_final_tsv.pkl",
      "meta": "/root/autodl-tmp/工具调用/API-Bank/新路由方法_apibank/final_results/saved_models/best_cg_tabm_meta_from_final_tsv.json"
    },
    "gaia": {
      "model": "/root/autodl-tmp/通用问题/GAIA/Qwen2.5-7B-Instruct/final_results/final_cg_tabm_router_gaia_full_epoch36.pth",
      "scaler": "/root/autodl-tmp/通用问题/GAIA/Qwen2.5-7B-Instruct/final_results/final_cg_tabm_robust_scaler_gaia_full_epoch36.pkl"
    },
    "task": {
      "model": "/root/autodl-tmp/任务拆解/中间过程/best_cg_tabm_router.pth",
      "scaler": "/root/autodl-tmp/任务拆解/中间过程/cg_tabm_robust_scaler.pkl"
    },
    "prog": {
      "model": "/root/autodl-tmp/代码问题/测试/中间过程/models/best_cg_tabm_router_apps.pth",
      "scaler": "/root/autodl-tmp/代码问题/测试/中间过程/models/cg_tabm_robust_scaler_apps.pkl",
      "meta": "/root/autodl-tmp/代码问题/测试/中间过程/models/cg_tabm_router_meta_apps.json"
    }
  },
  "proto_artifact": "/root/autodl-tmp/综合路由/v5的过程npz文件/proto_artifact_v4.npz"
}
```

### runtime_config.json — 运行时配置（热加载，修改即时生效）

格式与现有 `demo_5_runtime_config.json` 完全一致，不做改动：

```json
{
  "router_alias": "auto",
  "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
  "weights": { ... },
  "score_bands": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
  "tier_model_map": { "1": "gpt-5-4", ... },
  "model_providers": { ... }
}
```

## 统一日志方案

### 设计原则

- 全服务使用 Python 标准 `logging` 模块，不再使用自定义 `Demo5RequestLogger` 的独立 JSONL 写入
- 所有日志通过 `logging` 统一管理，支持 handler 配置（console + file rotation）
- 路由决策数据只写日志，不返回给客户端

### logging.py 职责

```python
# src/router_service/logging.py

import logging
import json
from logging.handlers import RotatingFileHandler

# 日志器名称约定
LOGGER_APP = "router_service"           # 通用应用日志
LOGGER_ROUTING = "router_service.routing"  # 路由决策专用日志
LOGGER_UPSTREAM = "router_service.upstream" # 上游调用日志

def setup_logging(log_dir: str = "logs", level: str = "INFO"):
    """服务启动时调用一次，配置所有 handler。"""
    ...
```

### 日志分类

| 日志器 | 用途 | 输出 |
|--------|------|------|
| `router_service` | 通用应用日志（启动、配置加载、错误） | console + `logs/app.log` |
| `router_service.routing` | 每次路由决策的完整记录（五路分数、proto 权重、tier、选中模型） | `logs/routing.jsonl`（JSON Lines 格式，便于分析） |
| `router_service.upstream` | 上游调用记录（模型、延迟、状态码、错误） | `logs/upstream.jsonl` |

### routing.jsonl 单条记录示例

```json
{
  "ts": "2026-04-15T14:30:00.123",
  "request_id": "chat-a1b2c3d4e5f6",
  "requested_model": "auto",
  "scores_0_2": {"纠错": 0.82, "工具调用": 1.15, "通用任务": 0.63, "任务拆解": 0.91, "编程": 0.44},
  "proto_weighted_0_2": 0.87,
  "total_score_0_10": 4.15,
  "score_source": "proto_weighted_0_2",
  "routing_tier": 4,
  "selected_model": "step-3-5-flash",
  "input_preview": "帮我写一个排序算法...",
  "messages_count": 3,
  "is_stream": true
}
```

### upstream.jsonl 单条记录示例

```json
{
  "ts": "2026-04-15T14:30:00.456",
  "request_id": "chat-a1b2c3d4e5f6",
  "selected_model": "step-3-5-flash",
  "provider_slug": "aiping",
  "upstream_model": "Step-3.5-Flash",
  "api_base": "https://aiping.cn/api/v1",
  "status_code": 200,
  "ok": true,
  "latency_ms": 1230.5,
  "is_stream": true,
  "response_preview": "以下是一个快速排序的实现..."
}
```

## 模块详细设计

### main.py

```python
# 启动入口
def create_app(
    runtime_config_path: str = "runtime_config.json",
    model_paths_config: str = "model_paths.json",
) -> FastAPI:
    setup_logging()
    app = FastAPI(title="Router Service", version="1.0.0")
    # lifespan 中初始化 router_engine、runtime_store
    app.include_router(chat_router, prefix="/v1")
    app.include_router(completions_router, prefix="/v1")
    app.include_router(meta_router)
    return app

def cli():
    """argparse 入口：--host, --port, --runtime-config, --model-paths"""
    ...
```

v3 改动：`invoke_selected_model` 不再作为启动参数，服务模式下始终调用上游。

### deps.py

```python
# 全局单例，lifespan 中初始化
_router_engine: HybridIntegratedDifficultyRouter | None = None
_runtime_store: RuntimeConfigStore | None = None

def get_runtime_store() -> RuntimeConfigStore: ...
def get_router_engine() -> HybridIntegratedDifficultyRouter: ...
def require_api_key(authorization: str | None = Header(None), x_api_key: str | None = Header(None)) -> str: ...
```

### routers/chat.py — v3 改动重点

```python
@router.post("/chat/completions")
def chat_completions(request, api_key, runtime_store, router_engine):
    config = runtime_store.load()

    # 路由决策
    route_result = None
    selected_model = request.model
    if request.model == config["router_alias"]:
        route_result = router_engine.predict_chat_messages(request.messages, ...)
        selected_model = route_result["weighted_routing"]["selected_model"]

        # [v3] 记录路由决策到日志（不返回给客户端）
        routing_logger.info(json.dumps({...}))

    # [v3] 始终调用上游，没有 route-only 分支
    target = resolve_model_provider_target(selected_model, config["model_providers"])
    litellm_response = litellm.completion(...)

    if is_stream:
        def _stream_sse():
            for chunk in litellm_response:
                chunk_dict = chunk.model_dump(exclude_none=True)
                # [v3] model 字段写实际模型名
                chunk_dict["model"] = selected_model
                # [v3] 不附加 router 字段
                yield f"data: {json.dumps(chunk_dict)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_stream_sse(), ...)
    else:
        payload = litellm_response.model_dump(exclude_none=True)
        # [v3] model 字段写实际模型名
        payload["model"] = selected_model
        # [v3] 不调用 _augment_chat_response，不注入 router 字段
        # [v3] 清理 <think> 标签
        return JSONResponse(content=payload)
```

### routers/completions.py — v3 同步清理

与 chat.py 同理：不注入 router 字段，不暴露路由数据，日志记录完整决策。

### services/router_engine.py

从 demo_5.py 迁移 `HybridIntegratedDifficultyRouter`，改动：

- 构造函数接收 `model_paths: dict` 参数（从 model_paths.json 加载），不再硬编码路径常量
- `predict_chat_messages()` 中删除 `_try_parse_proxy_route_payload()` 调用
- 删除 `invoke_selected_model` / `invoke_selected_model_chat()` 逻辑（上游调用由 router 层负责，engine 只做路由决策）
- 返回值中不再包含 `selected_model_invocation`

### utils/input_builder.py — v3 改动

`shared_record_from_chat_messages()`：
- 识别 `role="tool"` 消息，提取 tool result 内容
- 识别 assistant 消息中的 `tool_calls` 字段，提取工具名作为 action_space
- 处理 content 为块数组 `[{"type": "text", "text": "..."}]` 的情况（已由 `_stringify_message_content` 覆盖）

`build_full_llm_input_for_chat_messages()`：
- assistant 消息 content 为空但有 `tool_calls` 时，生成 `[Calling tools: name1, name2]` 占位文本
- `role="tool"` 消息转为 `[Tool result] ...` 并映射为 assistant role

不迁移 `_try_parse_proxy_route_payload()`。

## 不迁移的代码（从 demo_5.py 丢弃）

| 函数/逻辑 | 原因 |
|-----------|------|
| `_try_parse_proxy_route_payload()` | v3 无 proxy 格式 |
| `_augment_chat_response()` | v3 不暴露路由数据 |
| `_router_meta_from_route_result()` | 服务端不需要；cli.py 离线模式如需可单独保留 |
| `_build_router_headers()` 中的 Tier/Score header | v3 不暴露 |
| route-only 分支（`if not invoke_selected_model: return route_only_response`） | v3 始终调用上游 |
| `shared_record_from_openclaw_record()` | proxy 格式专用，v3 不需要 |
| `build_full_llm_input_for_other_routes()` | proxy 格式专用，v3 不需要 |
| `invoke_selected_model_request()` / `invoke_selected_model_chat()` | 上游调用改由 router 层通过 litellm 直接完成 |

## 依赖清单

```toml
[project]
name = "router-service"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "litellm>=1.40",
    "httpx>=0.27",
    "torch>=2.1",
    "transformers>=4.40",
    "numpy>=1.26",
    "pandas>=2.1",
    "scikit-learn>=1.4",
    "pydantic>=2.0",
]
```

## 启动方式

```bash
cd /root/autodl-tmp/router-service
uv sync
uv run router-service --port 8013
# 或
uv run python -m router_service.main --serve --port 8013
```

## 迁移验证

1. 启动新服务，发送 `model=auto` 的 chat completions 请求
2. 确认响应中无 `router` 字段、无 `X-Demo5-Routing-Tier` header
3. 确认 `logs/routing.jsonl` 中记录了完整路由决策
4. 确认 `logs/upstream.jsonl` 中记录了上游调用详情
5. 确认 `runtime_config.json` 热更新生效
6. 发送包含 tool_calls / tool role 的 messages，确认路由正常
