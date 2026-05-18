# Phase 5: Admin Domain Controllers - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 5-Admin Domain Controllers
**Areas discussed:** Admin 路径命名空间, 代理消除实现策略, Service Logs 数据源, 遗留决策 + 写入失效 hook

---

## Admin 路径命名空间

| Option | Description | Selected |
|--------|-------------|----------|
| 统一 /admin 前缀 | 全部 admin 端点加 /api/v1/admin/ 前缀，admin 前端调整 API_URL | ✓ |
| 只重命名 /auth/* 冲突 | 仅 /auth/admin/login 等冲突路径改，其他保留 | |
| 混合修复 | 仅 /admin/auth/* 加前缀，其他端点保持杂乱 | |

**User's choice:** 统一 /admin 前缀
**Notes:** D-01 锁定。整顿目前 admin-service 中 router 挂载不一致问题（有些已在 /admin 下、有些在根）。admin 前端需更新 API_URL — 用户已知该 trade-off。原 admin `controllers/model_catalog.py` 与 `controllers/internal.py` 因 Phase 4 D-01/D-06 已覆盖或后续 phase 重建，统一不迁移（D-01a/D-01b）。

---

## 代理消除实现策略

| Option | Description | Selected |
|--------|-------------|----------|
| 直接复用 Phase 4 user services | admin controller 直接 from api_service.services.xxx | |
| 新建 admin 域 service 包装 | 新建 admin_user_service / dashboard_service 等包装 Phase 4 services + 集中 audit | ✓ |
| 混合：repo + 跨域走 service | 直接调 Phase 3 repository，复杂查询走 admin_management_service | |

**User's choice:** 新建 admin 域 service 包装（Claude 推荐）
**Notes:** D-02 锁定。理由：架构边界清晰、audit 集中、跨域聚合自然、user services 不被污染、源已有 management_service.py 模式。新建 5 个 admin service：admin_user_service / dashboard_service / admin_voucher_service / admin_route_monitor_service / admin_service_logs_service。

---

## Service Logs 数据源

| Option | Description | Selected |
|--------|-------------|----------|
| 本地 + inference HTTP | 本地 RingBuffer + HMAC 调 inference-service /api/v1/internal/logs/* | ✓ |
| 仅本地 RingBuffer | 只返回 api-service 本地日志 | |
| 接入集中日志系统 | ELK / Loki | |

**User's choice:** 本地 + inference HTTP（Claude 推荐）
**Notes:** D-03 锁定。理由：遵循"纯重构不变行为"、基础设施就绪（RingBufferHandler、common.internal HMAC client、inference /internal/logs 已存在）、最小 diff（删 _REMOTE_SERVICES 中 user/router 两项）、降级行为保留。

---

## 遗留决策 + 写入失效 hook

### 子问 4a：Schemas/common 上移决策（Phase 4 D-03 延后项）

| Option | Description | Selected |
|--------|-------------|----------|
| 合并到 schemas/common.py | 单文件兼容 user/admin | |
| 上移到 common/schemas.py | infra 层 ApiResponse/DateTimeModel/BaseResponse | ✓ |
| 保持双份 | user/admin schemas/common.py 各自独立 | |

**User's choice:** 上移到 common/schemas.py
**Notes:** D-04 锁定。Phase 5 同步重构 Phase 4 已写代码的 import 路径。05-01 第一步执行，避免后续 plan 冲突。

### 子问 4b：mc:* 缓存失效策略（Phase 4 D-05 延后项）

| Option | Description | Selected |
|--------|-------------|----------|
| SCAN+DEL 全量失效 | 写后 SCAN_ITER('mc:*') + DEL | ✓ |
| 按 key 前缀精细失效 | vendor 写只清 mc:vendors:* | |
| 不失效接受 TTL | 3-5 min 延迟兜底 | |

**User's choice:** SCAN+DEL 全量失效
**Notes:** D-05 锁定。封装 model_catalog_service._invalidate_cache()，在 commit 后调用，mc keys 上限可控。

### 子问 4c：RoutingConfigCache 失效信号（为 Phase 6 纶定接口）

| Option | Description | Selected |
|--------|-------------|----------|
| 预留 Redis 信号 | Phase 5 写入信号，Phase 6 消费 | ✓ |
| Phase 5 不动，Phase 6 补全 | invalidation 逻辑全在 Phase 6 | |
| stub 函数占位 | 提前定义空 stub | |

**User's choice:** 预留 Redis 信号（纶定接口）
**Notes:** D-06 锁定。具体契约：`INCR routing_config:version`（Redis db/2）。Phase 6 RoutingConfigCache 每次 read 先 GET 版本号比对，不一致则 reload DB。无需 pub/sub 后台任务。

---

## Claude's Discretion

- Service 内 @staticmethod 模式沿用 Phase 4 决定（pool_service 599 行可内部分 section）
- bootstrap_service 触发：lifespan 启动钩子幂等创建超管
- Audit 写入失败：仅 log warning 不阻塞业务 mutation
- D-04 上移过程：05-01 第一步执行 schemas 上移 + Phase 4 import 修正

## Deferred Ideas

- HMAC 内部端点骨架（Phase 8 重建）
- 集中日志系统接入（超出重构范围）
- Audit log 装饰器/middleware 切面（长期优化）
- 超管 bootstrap CLI 命令（不在本次范围）
- Dashboard 聚合查询缓存（性能不达标时 Phase 9 评估）
- RoutingConfigCache 失效改 PUBLISH（Phase 6 实现时再评估）
