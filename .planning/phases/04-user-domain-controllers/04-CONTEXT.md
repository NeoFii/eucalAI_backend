# Phase 4: User Domain Controllers - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

将 user-service 的 4 个用户面 controller（auth/keys/billing/model_catalog）+ 对应 services + schemas 迁移到 api-service。所有前端面向的 HTTP 端点路径保持与现 user-service 完全一致（仅 host:port 改变），鉴权依赖复用 Phase 3 产出（`get_current_user`）。

迁移范围对应 ROADMAP success criteria：
1. 用户注册/登录/登出/refresh（cookie JWT，10 个 /auth/* 端点）
2. API Key CRUD（5 个 /keys 端点）
3. 余额/交易/用量查询（8 个 /billing 端点）
4. 公开模型目录查询（4 个 /model-vendors, /models, /models/categories, /models/{slug} 端点）
5. 邮件发送（注册验证码、密码重置）

不包含：
- admin 代理用的 7 个 `internal_*.py` 端点（D-01，全部不迁移）
- admin 域 controller（Phase 5）
- relay 协议端点 / API Key 转发期鉴权（Phase 6/7）
- inference-service HMAC 内部端点（Phase 8）

</domain>

<decisions>
## Implementation Decisions

### Internal Endpoints 处置
- **D-01:** Phase 4 完全不迁移 user-service 的 `internal_*.py`（7 个文件 ~1000 行）。Phase 5 admin controller 通过 Python `from api_service.services.xxx import XxxService` 直接调用 service 层，同进程无需 HMAC。HMAC-protected internal 端点是 Phase 8 inference-service 专用，与代理用 internal 无关。

### Email 发送执行模型
- **D-02:** Email 发送改为 ARQ 后台任务，controller 立即返回 200。
  - 实施附带影响（planner 处理）：
    - 现有 user-service ARQ worker（`src/core/worker.py` + `src/core/jobs.py`）一并迁移到 `api_service/core/worker.py`，包含 4 个既有 job：`aggregate_usage_stats` / `cleanup_expired_verification_codes` / `cleanup_expired_sessions` / `reconcile_balance_ledger`
    - 新增 `send_verification_email(ctx, email, code, purpose)` job
    - ARQ Redis pool client 在 lifespan 初始化（复用 Phase 2 已配置的 Redis db/1）
    - email_service 同步写 verification_code 行到 DB（保持事务一致性），随后 `await ctx['arq'].enqueue_job('send_verification_email', ...)` 投递
  - 失败处理：ARQ 自身重试 + 失败日志，前端不立即知晓发送结果（行为变化但可接受，因源行为 SMTP 失败时也无重试）

### Schemas 迁移布局
- **D-03:** Phase 4 按域 1:1 复制 user-service schemas：`schemas/{auth.py, billing.py, keys.py, common.py}`。`internal_*.py` schema 因 D-01 不迁移。
  - `schemas/common.py` 暂时直接复制 user-service 版（含 `ApiResponse[T]`, `DateTimeModel`, `AuthBaseResponse`, `AuthErrorResponse`）
  - admin-service 也有几乎相同的 `schemas/common.py`，是否合并/上移到 `common/schemas.py` **延后到 Phase 5 决定**
  - `ApiResponse[T]` envelope 模式保持不变（前端兼容约束）

### Model Catalog 数据源 + 范围
- **D-04:** `/models`, `/model-vendors`, `/models/categories`, `/models/{slug}` 查询 `model_catalog` 表（含 vendor + category），过滤逻辑与现 admin-service 内部端点一致，**不引入 pool_model_configs JOIN**（保留与现行前端 100% 行为一致）
- **D-05:** 保留 Redis 缓存层（mc: 前缀 + 源 TTL：vendors/categories 300s, models list 120s, model detail 300s）。Phase 5 admin 写入 model_catalog 时需主动 invalidate `mc:*` keys（admin domain 责任，记入 Phase 5 风险）
- **D-06:** Phase 4 **提前**从 admin-service 拷贝读路径 schemas 到 `api_service/schemas/model_catalog.py`（VendorListResponse, CategoryListResponse, SupportedModelListResponse, SupportedModelResponse 等只读 schema）。Phase 5 在此文件追加 admin CRUD 的写入 schemas
- **D-07:** Phase 4 新增 user 域的轻量 `model_catalog_service.py`，封装只读查询 + 缓存逻辑。Phase 5 在 admin 域单独建 admin model_catalog service 处理写入（两者共享 ModelCatalogRepository，由 Phase 3 D-04 提供）

### Plan 拆分（沿用 ROADMAP）
- **D-08:** 保留 ROADMAP 预定义的 3-plan 拆分：
  - 04-01: Auth controllers（/auth/* 10 个端点 + auth_service + schemas/auth.py + worker 迁移 + jobs.py 迁移）
  - 04-02: API Key + Billing controllers（/keys 5 + /billing 8 端点 + api_key_service + balance_service + topup_order_service + voucher_service + usage_stat_service + schemas/keys.py + schemas/billing.py）
  - 04-03: Model catalog + email service（/models 等 4 端点 + model_catalog_service + email_service + schemas/model_catalog.py + send_verification_email ARQ job）

### Claude's Discretion
- Service 层模式：源混用 @staticmethod 类 与 模块级单例（email_service）。统一采用 user-service CLAUDE.md 规定的 `@staticmethod + db: AsyncSession 首参` 模式；email_service 在保留 SMTP 配置状态的前提下也可改为 staticmethod（无状态 + 配置从 settings 读取）
- Router 挂载：源 controller 直接 `@router.post("/auth/register")`；可保留同样形式，也可改为 `APIRouter(prefix="/auth")` + 路径不含 /auth — 二者最终 URL 一致，planner 自选更清晰风格
- 异常映射：复用 `api_service/common/core/exceptions.py` 已有的 InvalidCodeException / CodeExpiredException / AuthenticationException 等
- 测试粒度：controller 集成测试 + service 单元测试，覆盖 happy path + 主要错误分支

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source Controllers (迁移源 — 端点签名/参数/响应权威参考)
- `services/user-service/src/controllers/auth.py` — 10 个 /auth/* 端点
- `services/user-service/src/controllers/keys.py` — 5 个 /keys 端点
- `services/user-service/src/controllers/billing.py` — 8 个 /billing 端点
- `services/user-service/src/controllers/model_catalog.py` — 4 个公开查询端点（注意：源码是 gateway 代理，合并后改为本地 service 调用）

### Source Services (迁移源 — 业务逻辑权威参考)
- `services/user-service/src/services/auth_service.py` — 393 行
- `services/user-service/src/services/api_key_service.py` — 196 行
- `services/user-service/src/services/balance_service.py` — 411 行
- `services/user-service/src/services/email_service.py` — 172 行（注意：D-02 改为 ARQ 投递）
- `services/user-service/src/services/topup_order_service.py` — 82 行
- `services/user-service/src/services/usage_stat_service.py` — 338 行
- `services/user-service/src/services/voucher_service.py` — 185 行

### Source Schemas (迁移源 — D-03 范围)
- `services/user-service/src/schemas/auth.py` — 225 行
- `services/user-service/src/schemas/billing.py` — 190 行
- `services/user-service/src/schemas/keys.py` — 83 行
- `services/user-service/src/schemas/common.py` — 40 行（`ApiResponse[T]`, `DateTimeModel`, `AuthBaseResponse`）

### Source ARQ Worker (D-02 一并迁移)
- `services/user-service/src/core/worker.py` — WorkerSettings 装配
- `services/user-service/src/core/jobs.py` — 4 个既有 job 定义 + `build_redis_settings()`

### Cross-Domain (admin-service 提前读 — D-06)
- `services/admin-service/src/schemas/model_catalog.py` — 拷贝只读 Response schemas 到 api-service
- `services/admin-service/src/services/model_catalog_service.py` — 参考只读查询逻辑

### Phase 3 产出（已就绪）
- `services/api-service/api_service/core/dependencies/user.py` — `get_current_user` 依赖
- `services/api-service/api_service/repositories/user_repository.py` — Phase 3 D-04 合并的 user + session + email_code
- `services/api-service/api_service/repositories/api_key_repository.py` — ApiKeyRepository
- `services/api-service/api_service/repositories/billing_repository.py` — balance_tx + topup_order + usage_stat
- `services/api-service/api_service/repositories/voucher_repository.py` — VoucherRepository
- `services/api-service/api_service/repositories/model_catalog_repository.py` — vendor/category/model 操作
- `services/api-service/api_service/core/router.py` — `api_router` 等待 Phase 4 挂载 user 域路由

### Phase 2 产出（已就绪）
- `services/api-service/api_service/core/db.py` — `get_db` 依赖
- `services/api-service/api_service/common/observability.py` — `log_event`, `set_uid`
- `services/api-service/api_service/common/utils/{jwt,password,nanoid_uid,snowflake,timezone}.py`
- `services/api-service/api_service/common/core/exceptions.py` — 业务异常层级

### Architecture / 项目约束
- `docs/architecture-refactoring.md` — 合并架构方案（HTTP→直接调用，CallLogBuffer→直写）
- `services/user-service/CLAUDE.md` — service 层 @staticmethod / 异步规范 / 日志规范（同样适用于 api-service user 域）
- `CLAUDE.md` (project root) — 用户标识规范（user_uid: str 对外，user_id: int 内部）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Base` + Mixins（TimestampMixin, SoftDeleteMixin）已在 `common/infra/db/base.py`（Phase 2）
- `get_db` 异步生成器已在 `core/db.py`（Phase 2）
- `get_current_user` 依赖已在 `core/dependencies/user.py`（Phase 3 D-06/D-08）
- JWT 工具 `create_access_token`, `create_refresh_token`, `decode_token`, `get_token_jti` 在 `common/utils/jwt.py`
- 异步密码 `hash_password_async`, `verify_password_async` 在 `common/utils/password.py`
- NanoID `generate_nanoid_uid` 在 `common/utils/nanoid_uid.py`
- Snowflake `generate_snowflake_id` 在 `common/utils/snowflake.py`
- 业务异常：AuthenticationException / InvalidTokenException / InvalidCodeException / CodeExpiredException / CodeNotFoundException / NotFoundException / ValidationException
- 所有 Phase 3 repository 类（共 10 个，按域分组）
- Settings 单例从 `core.config` 注入（Phase 1 合并 settings）

### Established Patterns
- Controller 薄层：参数提取 → service 调用 → ApiResponse 构造
- Service @staticmethod：第一参数 `db: AsyncSession`，模块外按需 import
- Repository pattern：BaseRepository[T] + `get_list(ListParams)` 分页 + `options=[selectinload(...)]` eager loading
- 阻塞 IO 必须 `asyncio.to_thread`（bcrypt 已封装 async 版本）
- 余额操作 `SELECT ... FOR UPDATE` 行锁 + 显式 commit
- 日志：`log_event(logger, level, "eventName", key=value)`，禁止字符串拼接
- 配置：`from api_service.core.config import settings`，单例已在 Phase 1 落地

### Integration Points
- `api_service/core/router.py` — Phase 4 controllers 在此 include_router
- `api_service/core/lifespan.py` — Phase 4 注册 ARQ Redis pool 初始化 + shutdown
- 前端调用：`POST /api/v1/auth/login` 等路径不变，仅切换 host:port

### 已识别风险点
- email_service 改 ARQ 后，注册流程从"同步发送邮件 + 返回"变成"异步投递 + 返回"。前端如果根据 200 显示"邮件已发送"，行为不变；如果前端依赖错误响应判断发送失败，需要 Phase 9 验证
- D-05 缓存失效：admin 修改 model_catalog 时需通知 mc:* keys 失效。Phase 4 完成时缓存只增不删，正确性由 TTL 兜底；Phase 5 admin 写入时补齐 invalidation 逻辑

</code_context>

<specifics>
## Specific Ideas

- API Key 创建响应中明文 key 只返回一次（源码 D-02 行为，保留）
- 余额查询应优先使用 `SELECT ... FOR UPDATE` 行锁的对应 read 版本（无锁），避免不必要的锁竞争
- voucher 兑换是金额变更，必须走 `SELECT ... FOR UPDATE` + ref_id 幂等
- /billing/usage 三个端点（usage/analytics/logs）粒度不同：summary、按时间段聚合、按 call_log 明细；分别走不同 repository 方法
- /auth/me 端点只返回当前用户基本信息（不含敏感字段），通过 `get_current_user` 依赖直接产出
- email_service 的 ARQ job 应包含 retry_jitter + max_tries 配置（默认 ARQ 已支持）

</specifics>

<deferred>
## Deferred Ideas

- **统一 BaseResponse / DateTimeModel 到 common/schemas**：Phase 5 同时处理 admin schemas 时一起决定。Phase 4 暂时保留 schemas/common.py 副本。
- **model_catalog 缓存失效机制**：admin 写入时主动 invalidate `mc:*` keys 的实现在 Phase 5。Phase 4 完成时缓存只增不删，admin 修改后用户最多看到 5min 旧数据（TTL 兜底）。
- **/models 是否过滤掉无 channel 配置的项**：当前选 D-04 与现行前端 100% 一致（不过滤）。如未来产品上需要"只显示可用模型"，可改为 D-04 选项 3（两表 JOIN），属于功能调整不在本次重构。
- **Email 发送失败的前端反馈机制**：D-02 行为差异（异步投递后无法立即反馈 SMTP 错误）。如果产品上需要"邮件发送失败"提示，将来可加 webhook / 状态轮询接口，超出本次重构范围。

</deferred>

---

*Phase: 4-User Domain Controllers*
*Context gathered: 2026-05-19*
