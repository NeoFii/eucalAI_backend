# Phase 4: User Domain Controllers - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 4-User Domain Controllers
**Areas discussed:** Internal endpoints 处置, Email 发送执行模型, Schemas 迁移布局, Model catalog 数据源 + 范围

---

## Internal Endpoints 处置

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 4 完全不迁移 | internal_*.py 全部不抄到 api-service；Phase 5 admin controller 直接 import service 层 | ✓ |
| Phase 4 临时保留，Phase 5 删除 | 整体迁移（带 HMAC），Phase 5 完成后再删 | |
| 只保留 HMAC 骨架 | 删除 admin 代理用 internal_*，但保留 Phase 8 inference-service 需要的 HMAC 端点结构 | |

**User's choice:** Phase 4 完全不迁移
**Notes:** Claude 推荐方案理由：admin controller 与 user service 同进程，可直接 Python import 调用，根本不需要 HMAC；Phase 8 HMAC 是为 inference-service 跨进程通信，与代理用 internal 无关；避免 ~1000 行作废代码。User 同意采用建议（D-01）。

---

## Email 发送执行模型

| Option | Description | Selected |
|--------|-------------|----------|
| 保持同步（asyncio.to_thread） | 1:1 迁移现状，SMTP 阻塞请求 500-2000ms，失败同步反馈 | |
| 投递 ARQ 后台任务 | controller 立即返回 200，worker 后台调 SMTP，可自动重试 | ✓ |
| 混合执行 | 关键路径同步，非关键 ARQ | |

**User's choice:** 投递 ARQ 后台任务
**Notes:** D-02 锁定。附带影响：现有 user-service ARQ worker（4 个 job）一并迁移到 api_service/core/worker.py；新增 send_verification_email job；ARQ Redis pool 在 lifespan 初始化复用 Phase 2 db/1。失败响应行为变更：用户无法立即知晓 SMTP 失败（可接受，源行为 SMTP 失败也无重试）。

---

## Schemas 迁移布局 + 范围

| Option | Description | Selected |
|--------|-------------|----------|
| 提升到 common/schemas | ApiResponse / DateTimeModel 放 api_service/common/schemas.py，跨域复用 | |
| schemas/common.py | 放 schemas/common.py，与源结构一致 | |
| 延后决定 | Phase 4 只拷 user-service common.py，Phase 5 决定是否与 admin 合并 | ✓ |

**User's choice:** 延后决定
**Notes:** D-03 锁定 — Phase 4 按域 1:1 复制（auth/billing/keys/common），internal_*.py schemas 因 D-01 不迁移。admin 与 user 的 common.py 合并/上移问题留给 Phase 5。

---

## Model Catalog 数据源 + 范围

| Option | Description | Selected |
|--------|-------------|----------|
| model_catalog 表（同现状） | 查 model_catalog，过滤 enabled，与现行前端一致 | ✓ |
| pool_model_configs 表 | 只列已配 channel 的，语义"可调通" | |
| 两表 JOIN | model_catalog ∩ pool_model_configs，"可上架且可调通" | |

**User's choice:** model_catalog 表（同现状）
**Notes:** D-04 锁定。保持与现行前端 100% 行为一致，不引入 JOIN。

### 后续追问 1：缓存策略

| Option | Description | Selected |
|--------|-------------|----------|
| 去除缓存 | 每次直查 DB | |
| 保留 Redis 缓存（同源） | mc: 前缀 + 120-300s TTL | ✓ |
| 进程内 TTLCache | cachetools 进程内，4 workers 独立 | |

**User's choice:** 保留 Redis 缓存（同源）
**Notes:** D-05 锁定。保持现行性能特性。admin 写入时主动 invalidate `mc:*` keys 的逻辑延后到 Phase 5（Phase 4 完成时缓存只增不删，TTL 兜底）。

### 后续追问 2：响应 schema

| Option | Description | Selected |
|--------|-------------|----------|
| raw dict（同源） | repository→service→JSONResponse | |
| 提前迁移读 schemas | 从 admin-service 拷读路径 schemas 到 api-service | ✓ |

**User's choice:** 提前迁移读 schemas
**Notes:** D-06/D-07 锁定。Phase 4 拷贝 admin-service `schemas/model_catalog.py` 的只读 schemas（VendorListResponse, SupportedModelListResponse 等）到 api_service/schemas/model_catalog.py。Phase 5 在此文件追加 admin CRUD 写入 schemas。新增 user 域 model_catalog_service（只读 + 缓存）。验证标准：输出字段与现行 raw dict 一致以保前端兼容。

---

## Claude's Discretion

- Service 层模式：统一采用 user-service CLAUDE.md 规定的 `@staticmethod + db: AsyncSession` 模式。email_service 在保留 SMTP 配置状态的前提下可改为 staticmethod。
- Router 挂载形式：APIRouter prefix 写法 vs 内联完整路径，planner 自选（最终 URL 必须一致）。
- 异常映射：复用 api_service/common/core/exceptions.py 已有的业务异常类。
- 测试粒度：controller 集成测试 + service 单元测试，覆盖 happy path + 主要错误分支。

## Deferred Ideas

- 统一 BaseResponse / DateTimeModel 到 common/schemas（Phase 5 决定）
- model_catalog 缓存失效机制（Phase 5 admin 写入时实现）
- /models 是否过滤无 channel 模型（产品功能调整，不在本次重构）
- Email 发送失败的前端反馈机制（webhook/状态轮询，超出重构范围）
