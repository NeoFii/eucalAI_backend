# Phase 7: Protocol Adapters & Streaming - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 07-protocol-adapters-streaming
**Areas discussed:** CallLifecycle 移植策略, SDK Client Pool + 上游调用, SSE 流式响应处理, 三级速率限制实现

---

## CallLifecycle 移植策略

| Option | Description | Selected |
|--------|-------------|----------|
| 保留 CallLifecycle 类，内部重接 Phase 6 模块 | 保持 CallLifecycle 类的整体结构，但内部调用改为 Phase 6 的模块 | ✓ |
| 拆解为 controller 层线性调用 | 不要单独的 CallLifecycle 类，直接在 controller 中线性编排 | |
| 保留编排器但拆分文件 | 保留 CallLifecycle 作为编排器，但拆分为多个小文件 | |

**User's choice:** 保留 CallLifecycle 类，内部重接 Phase 6 模块

### 文件位置

| Option | Description | Selected |
|--------|-------------|----------|
| relay/call_lifecycle.py 单文件 | 放在 relay/ 下单文件，可能 400+ 行 | |
| relay/lifecycle/ 目录拆分 | 新建目录，拆分为 orchestrator.py + stream.py + finalize.py | ✓ |

**User's choice:** relay/lifecycle/ 目录拆分

---

## SDK Client Pool + 上游调用

| Option | Description | Selected |
|--------|-------------|----------|
| 原样移植 SdkClientPool | 直接移植 threading.Lock + LRU OrderedDict | ✓ |
| 移植但换 asyncio.Lock | 用 asyncio.Lock 替换 threading.Lock | |
| 改为预创建客户端池 | 不用 LRU，改为每个 channel 预创建客户端 | |

**User's choice:** 原样移植 SdkClientPool

---

## SSE 流式响应处理

**User's input:** 建议参考 autodl-tmp/new-api-main 的设计，如果做得更好就借鉴

### 研究 new-api 后的方案选择

| Option | Description | Selected |
|--------|-------------|----------|
| 借鉴 new-api Adaptor 模式 + 保留双路径 | StreamConverter 负责 chunk 格式转换，流迭代统一在 lifecycle/stream.py，Anthropic 原生透传保留 | ✓ |
| 强制单路径（全部转换） | 统一为单路径，Anthropic→Anthropic 也经过转换 | |
| 每个 Adaptor 完全内化流式 | 类似 new-api DoResponse 完全内化 | |

**User's choice:** 借鉴 new-api Adaptor 模式 + 保留双路径

---

## 架构方向（综合对比）

| Option | Description | Selected |
|--------|-------------|----------|
| 保留现有分层 + 借鉴 new-api 重试/计费模式 | 保留 CallLifecycle + ProtocolAdapter 分层，借鉴 new-api 的重试循环和 BillingSession 生命周期 | ✓ |
| 完全对标 new-api Adaptor 模式 | Adaptor 包含 DoRequest + DoResponse | |
| 混合：重试循环提升到 lifecycle 层 | 保留 CallLifecycle 但重试从 upstream_caller 提升到 lifecycle | ✓ |

**User's choice:** 保留现有分层 + 借鉴 new-api 重试/计费模式；重试循环提升到 lifecycle 层

---

## 三级速率限制实现

| Option | Description | Selected |
|--------|-------------|----------|
| 统一用 token bucket | 三级都用 token bucket 算法，单一 Lua 脚本 | ✓ |
| 原样移植（混用两种算法） | global/account 用 sliding window，user 用 token bucket | |
| 统一用 sliding window | 三级都用 sliding window | |

**User's choice:** 统一用 token bucket

### 检查顺序

| Option | Description | Selected |
|--------|-------------|----------|
| global → per-user → per-key（大到小） | 先检查最大范围，早拒绝减少 Redis 调用 | ✓ |
| per-key → per-user → global（小到大） | 先检查最小范围 | |
| 并行检查（Redis pipeline） | 三级并行发送 | |

**User's choice:** global → per-user → per-key（大到小）

---

## GET /v1/models 端点

| Option | Description | Selected |
|--------|-------------|----------|
| 基于用户权限过滤 | 从 RoutingConfigCache 读取全量模型，结合 token 的 allowed_models 过滤 | ✓ |
| 返回全量模型（不过滤） | 返回所有已配置模型 | |

**User's choice:** 基于用户权限过滤

---

## Claude's Discretion

- ProtocolAdapter 的具体方法签名和内部组织
- Anthropic Messages adapter 的 parse_request 实现细节
- 非流式响应的具体字段清理逻辑
- 429 响应的 Retry-After header 计算方式
- /v1/models 响应中的 model metadata 字段

## Deferred Ideas

- Responses 协议的 background mode
- WebSocket realtime 协议
- per-model 限流
- 限流的动态配置热更新
