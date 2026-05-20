# EucalAI Backend — Architecture Consolidation

## What This Is

LLM API 中转平台后端，提供用户鉴权、API Key 管理、计费、模型路由、多协议转发（OpenAI/Anthropic/Responses）和管理后台功能。当前从 4 微服务合并为 2 服务（api-service + inference-service），消除不必要的跨服务 HTTP 调用。

## Core Value

用户通过 API Key 调用 LLM 转发端点时，请求必须低延迟、高可靠地完成鉴权→路由→转发→计费全链路。

## Requirements

### Validated

- ✓ 用户注册/登录/JWT 鉴权 — existing (user-service)
- ✓ 管理员 CRUD + 超管引导 — existing (admin-service)
- ✓ API Key 创建/验证/管理 — existing (user-service)
- ✓ 余额/交易/用量计费 — existing (user-service)
- ✓ Pool/Channel 管理 — existing (admin-service)
- ✓ 模型目录 CRUD — existing (admin-service)
- ✓ 路由配置管理 — existing (admin-service)
- ✓ OpenAI Chat/Anthropic Messages/Responses 协议转发 — existing (router-service)
- ✓ ML 分类路由 (Qwen2.5-7B + CG-TabM) — existing (inference-service)
- ✓ Call Log 记录 + 用量统计 — existing (user-service + router-service)
- ✓ 审计日志 — existing (admin-service)
- ✓ 仪表盘统计 — existing (admin-service → user-service)
- ✓ 兑换码系统 — existing (admin-service → user-service)
- ✓ Route Monitor — existing (admin-service → user-service)
- ✓ Service Logs 查询 — existing (admin-service → user-service)
- ✓ HMAC 签名内部通信 — existing (all services)
- ✓ 熔断器 + 重试 — existing (common/internal.py)

### Active

- [ ] 合并 admin-service + user-service + router-service 为 api-service
- [ ] 消除所有 admin→user HTTP 代理调用（直接调 service 层）
- [ ] 消除 router→user HTTP 调用（API Key 验证、计费、call log 直接 DB）
- [ ] 替换 ConfigManager HTTP 轮询为 RoutingConfigCache（DB + Redis 60s TTL）
- [ ] 替换 CallLogBuffer 批量 HTTP 为 asyncio.create_task 直接写 DB
- [ ] 合并两个数据库为单一 eucal_ai
- [ ] 统一三种鉴权模式共存（User JWT / Admin JWT / API Key / HMAC Internal）
- [ ] 保留 inference-service 独立部署在 GPU 服务器
- [ ] 更新 inference-service 指向新 api-service 端点

### Out of Scope

- 功能新增 — 本次纯重构，不改变用户可见行为
- 前端改动 — 仅更新 API_URL 配置指向
- inference-service 内部逻辑变更 — 只改 URL 指向
- 数据库 schema 变更 — 合并库但不改表结构

## Context

- 部署拓扑：Server 1 (2h4g CPU) = api-service + MySQL + Redis；Server 2 (GPU) = inference-service
- 参考项目：new-api（Go 分层单体）的架构模式
- 当前 admin-service ~80% 操作是代理转发到 user-service
- router-service 每个请求 3 次 HTTP 调用可消除（api-key validate, call-log batch, config refresh）
- Snowflake ID 无冲突（worker_id=1 user, worker_id=2 admin）
- 两库无表名冲突，可安全合并

## Constraints

- **部署**: api-service 必须适配 2h4g 服务器（4 workers × ~350MB ≈ 1.4GB + MySQL + Redis）
- **兼容性**: 前端 API 接口路径保持不变，仅改 host:port
- **零停机**: 需要并行运行验证后切换
- **技术栈**: Python 3.10+, FastAPI, SQLAlchemy 2.x async, Pydantic v2, Redis, ARQ

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 合并为 api-service + inference-service | GPU 需求是唯一真正的部署边界 | — Pending |
| Relay 放 CPU 服务器 | 消除跨网络 HTTP 调用，降低延迟 20-50ms | — Pending |
| 合并为单库 eucal_ai | 两库无冲突，合并后可建真正外键 | — Pending |
| RoutingConfigCache 替代 HTTP 轮询 | DB + Redis 60s TTL，admin 写入时主动失效 | — Pending |
| 直接 DB 写入替代 CallLogBuffer | 同进程内无需缓冲+批量 HTTP | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-19 after Phase 05 (admin-domain-controllers) complete — all admin controllers (69 endpoints across 11 controllers) ported into api-service. 5 HTTP gateway proxies eliminated, replaced with same-process service calls. Admin auth, audit logging, pool/model-catalog/routing CRUD, health-check ARQ cron all operational. 184 tests passing.*
