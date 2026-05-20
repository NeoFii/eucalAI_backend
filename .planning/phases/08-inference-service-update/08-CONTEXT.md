# Phase 8: Inference Service Update - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

在 api-service 上暴露 HMAC 签名保护的 `/api/v1/internal/routing-config/active/inference` 端点，供 inference-service 拉取路由配置。同时更新 inference-service 的配置和 gateway 代码，使其指向 api-service 而非 admin-service。

不包含：
- /active/full 端点（relay 已内置，直接读 RoutingConfigCache）
- 其他 admin-service internal 端点（admins/{uid}、rate-limits、model-catalog）— 合并后不再需要跨服务调用
- inference-service 内部 ML 逻辑变更

</domain>

<decisions>
## Implementation Decisions

### 端点路径设计
- **D-01:** api-service 上的 internal 端点保持原路径 `/api/v1/internal/routing-config/active/inference` 不变，与 admin-service 完全一致
- **D-02:** inference-service gateway 只需改 base URL，请求路径零改动

### allowed_callers 策略
- **D-03:** 只移植 `/active/inference` 一个端点，`allowed_callers={"inference-service"}`
- **D-04:** 不移植 `/active/full`（relay 已内置 RoutingConfigCache，无需 HTTP 拉取）
- **D-05:** 不移植其他 internal 端点（admins/{uid}、rate-limits、model-catalog）— 合并后这些调用已消除

### 切换策略
- **D-06:** inference-service 新增 `API_SERVICE_URL` 配置项（InferenceSettings 类），gateway 改用此配置
- **D-07:** `ADMIN_SERVICE_URL` 保留但标记 deprecated（注释说明），不删除以免破坏现有部署脚本
- **D-08:** gateway 类名从 `AdminConfigGateway` 改为 `ApiServiceConfigGateway`，文件名从 `admin_config.py` 改为 `api_service_config.py`，所有引用同步更新

### Claude's Discretion
- api-service internal controller 的具体文件组织（独立文件 vs 放入现有 controller）
- 端点的 response_model 是否复用 admin-service 的 Pydantic schema 或重新定义
- `API_SERVICE_URL` 的默认值选择

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### admin-service 原始实现（移植源）
- `services/admin-service/src/controllers/internal.py` — 原始 /routing-config/active/inference 端点实现，包含 InternalRoutingConfigInference schema 和 allowed_callers 配置
- `services/admin-service/src/services/routing_setting_service.py` — resolve_for_internal() 方法（已移植到 api-service）

### api-service HMAC 基础设施（已就绪）
- `services/api-service/api_service/common/http/internal_auth.py` — build_internal_auth_dependency() 验证端
- `services/api-service/api_service/common/http/internal_signing.py` — HMAC 签名原语（canonicalize + sign）
- `services/api-service/api_service/core/router.py` — 路由挂载点（已预留 Phase 8 注释）

### api-service 已就绪的 service 层
- `services/api-service/api_service/services/admin/routing_setting_service.py` — RoutingSettingService.resolve_for_internal(db)

### inference-service 需要修改的文件
- `services/inference-service/src/inference_service/gateways/admin_config.py` — AdminConfigGateway（将改名为 ApiServiceConfigGateway）
- `services/inference-service/src/inference_service/core/config.py` — InferenceSettings（新增 API_SERVICE_URL）
- `services/inference-service/src/inference_service/services/config_manager.py` — ConfigManager（gateway 注入点）
- `services/inference-service/src/common/internal.py` — HMAC 签名客户端（无需改动，只是参考）

### Architecture
- `docs/architecture-refactoring.md` — 合并架构方案

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_internal_auth_dependency(secret, request_ttl_seconds, allowed_callers)` — api-service 已有完整的 HMAC 验证 dependency
- `RoutingSettingService.resolve_for_internal(db)` — 返回 route_order、weights、score_bands、tier_model_map 等字段，已在 Phase 5 移植就绪
- `InternalRoutingConfigInference` Pydantic schema — admin-service 已定义，可直接复制

### Established Patterns
- api-service controller 使用 `Depends(get_db_session)` 注入 DB session
- internal 端点使用独立的 `verify_*` dependency 做 HMAC 验证
- inference-service gateway 继承 `BaseGateway`，在 `__init__` 中声明 base_url/timeout

### Integration Points
- `api_service/core/router.py` — 需要 include_router 挂载 internal controller
- `api_service/core/config.py` — Settings 类需要确认 INTERNAL_SECRET 和 INTERNAL_REQUEST_TTL_SECONDS 已存在
- inference-service `main.py` lifespan — gateway 实例化点（需要改类名和 import）

</code_context>

<specifics>
## Specific Ideas

- 端点实现几乎是 admin-service `get_active_routing_config_inference()` 的直接复制，调用 `RoutingSettingService.resolve_for_internal(db)` 后构造响应
- inference-service 的 ConfigManager 和 poll loop 逻辑完全不变，只是 gateway 指向新地址
- version 字段目前 admin-service 硬编码返回 0，api-service 可以考虑返回 routing_config:version 的实际值（但这是 Claude's discretion）

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 8-Inference Service Update*
*Context gathered: 2026-05-19*
