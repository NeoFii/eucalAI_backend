# Phase 8: Inference Service Update - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 08-inference-service-update
**Areas discussed:** 端点路径设计, allowed_callers 策略, 切换策略与兼容

---

## 端点路径设计

| Option | Description | Selected |
|--------|-------------|----------|
| 保持原路径不变 | api-service 上挂载 /api/v1/internal/routing-config/*，inference-service 只改 base URL，gateway 代码零改动 | ✓ |
| 新路径风格 | 改为 /internal/v1/routing-config/*，与 relay 端点路径风格区分。需要同时改 inference-service gateway 路径 | |

**User's choice:** 保持原路径不变
**Notes:** 最小变更、最安全的方案

---

## allowed_callers 策略

| Option | Description | Selected |
|--------|-------------|----------|
| 只保留 inference 端点 | 只移植 /active/inference，allowed_callers={"inference-service"}。/active/full 不移植 | ✓ |
| 两个端点都移植 | 两个端点都移植，以备将来可能有其他服务需要完整配置 | |
| 全量移植 internal 端点 | 移植 /active/inference + admins/{uid} + rate-limits + model-catalog | |

**User's choice:** 只保留 inference 端点
**Notes:** relay 已内置 RoutingConfigCache，其他 internal 端点合并后不再需要跨服务调用

---

## 切换策略与兼容

| Option | Description | Selected |
|--------|-------------|----------|
| 改现有配置值 | 直接把 ADMIN_SERVICE_URL 改为 api-service 地址。简单但配置名不准确 | |
| 新增 API_SERVICE_URL 配置 | 新增配置项，gateway 改用新配置。语义更清晰，需要改 gateway 代码 + settings 类 | ✓ |
| 新配置 + fallback | 新增 API_SERVICE_URL，同时支持 fallback 到 ADMIN_SERVICE_URL | |

**User's choice:** 新增 API_SERVICE_URL 配置
**Notes:** ADMIN_SERVICE_URL 保留但标记 deprecated

---

## Gateway 类名

| Option | Description | Selected |
|--------|-------------|----------|
| 改名为 ApiServiceConfigGateway | 反映实际调用目标，清晰但需要改文件名 + 所有引用 | ✓ |
| 保持 AdminConfigGateway 不变 | 最小变更，但名称与实际不符 | |

**User's choice:** 改名为 ApiServiceConfigGateway
**Notes:** 文件名从 admin_config.py 改为 api_service_config.py

---

## Claude's Discretion

- api-service internal controller 的文件组织
- response_model schema 是否复用或重新定义
- API_SERVICE_URL 的默认值
- version 字段是否返回 routing_config:version 实际值

## Deferred Ideas

None — discussion stayed within phase scope
