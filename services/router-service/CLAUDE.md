# Router-Service 开发规范

## 项目概述

router-service 是无状态 API 网关，负责接收 OpenAI 兼容请求、鉴权、智能路由、上游 LLM 调用、计费和日志记录。无数据库，所有持久化通过 HTTP 委托给 user-service 和 admin-service。

## 架构约束

- **无数据库**：状态存储于 Redis（限流、亲和性）或内存（配置缓存、API key 缓存、call-log 缓冲区）
- **上游调用统一走 litellm**：所有 LLM provider 通过 `litellm.acompletion` + `custom_llm_provider="openai"` 调用
- **内部服务通信统一走 `common/internal.py`**：HMAC 签名 + 连接池 + 熔断器 + 重试

## 连接池规范

- 内部服务调用使用 `InternalHttpPool`（共享 `httpx.AsyncClient`），在 lifespan 中初始化和关闭
- `InferenceClient` 拥有独立的持久化 `httpx.AsyncClient`
- **禁止**在请求处理路径中创建临时 `httpx.AsyncClient`

## Gateway 规范

- Gateway 是实例类，通过 `__init__` 注入依赖（settings、buffer 等）
- Gateway 实例在 `init_globals()` 中创建，通过 `get_*_gateway()` 获取
- **禁止**在 Gateway 方法内延迟导入 `get_settings()` 或其他全局依赖
- **禁止**使用 `@staticmethod` + 继承的反模式

## 异步/阻塞规范

- 请求处理路径必须全异步，禁止同步阻塞 I/O
- 文件 I/O 使用 `asyncio.to_thread()` 包装（参考 `RuntimeConfigStore.aload()`）
- `threading.Lock` 仅用于亚微秒级内存操作（如 `ChannelSelector` 计数器），禁止保护 I/O 操作
- Redis 操作使用 `redis.asyncio`

## 控制器规范

- 控制器只负责请求解析、响应格式化和日志记录
- 重试逻辑统一使用 `services/upstream_caller.py` 的 `upstream_call_with_retry()`
- **禁止**在循环或异常处理块内延迟导入
- 所有导入放在文件顶部

## 封装规范

- 禁止访问其他模块的私有属性（`_` 前缀）
- 需要跨模块访问的状态必须通过公开方法暴露
- 函数/方法如果被其他模块使用，不应以 `_` 开头

## 配置规范

- `common/config.py` 的 `BaseServiceSettings` 只包含 router-service 需要的字段
- 服务特有配置放在 `core/config.py` 的 `RouterSettings`
- 运行时路由配置通过 `ConfigManager` 三级加载：admin-service → cached_previous → local_fallback
- API key 等敏感值支持 `${ENV_VAR}` 插值

## 日志规范

- 使用 `common/observability.py` 的结构化 JSON 日志
- 三个专用 logger：`router_service`（应用）、`router_service.routing`（路由决策 JSONL）、`router_service.upstream`（上游调用 JSONL）
- 敏感数据（API key、密码、token）必须经过脱敏处理
- 使用 `log_event()` 发出结构化事件，禁止拼接字符串日志

## 安全规范

- 响应体和响应头禁止暴露内部路由信息（provider、channel、config version）
- 内部服务调用使用 HMAC-SHA256 签名 + 时间戳防重放（30s TTL）
- `INTERNAL_SECRET` 最少 32 字符
- 上游 URL 必须经过 `_validate_upstream_url()` 校验

## 并发安全

- `ChannelSelector.report_failure()` 等涉及读-判断-写的操作必须在单次锁获取内完成，避免 TOCTOU 竞态
- `update_health_cache()` 使用整体替换（非增量更新）保证一致性

## 依赖注入

- 使用模块级 service locator 模式（`init_globals()` + `get_*()` 函数）
- 所有全局单例在 lifespan startup 中初始化，shutdown 中清理
- `get_*()` 函数在未初始化时抛出 `RuntimeError`

## 构建与工具

- 包管理：uv（锁文件 `uv.lock`）
- 构建系统：hatchling
- Lint：`ruff check src/`（target py310, line-length 100）
- 类型检查：`mypy src/ --strict`
- 运行：`uvicorn src.main:app --host 0.0.0.0 --port 8003`
- 健康检查：`scripts/runtime_probe.py http-ready --port 8003`
