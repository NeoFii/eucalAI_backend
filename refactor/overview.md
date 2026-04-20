# 全项目架构重构指南

> 本文档不仅描述怎么改，更解释每个决策的原因、权衡和来源。
>
> 参考项目：
> - **[A]** arctikant/fastapi-modular-monolith-starter-kit — 模块化单体，Gateway/Event/Policy/BaseRepository
> - **[B]** fastapi/full-stack-fastapi-template — FastAPI 官方模板，扁平 CRUD 层，deps.py 集中依赖
> - **[C]** zhanymkanov/fastapi-best-practices — 17k star 最佳实践文档，按域组织、迁移规范、async/sync 决策

---

## 第一部分：设计原则与决策论证

### 1. 为什么引入 Repository 层

**当前问题**

三轮审计反复出现同一个模式：Service 方法里同时做业务判断和拼 SQL。比如 `balance_service.py` 的 `freeze()` 在一个方法里完成了行锁查询、幂等检查、余额计算、流水写入。当需要改查询逻辑（比如加 `SELECT FOR UPDATE`）时，必须同时理解业务规则才能确定改动是否安全。当需要测试业务规则时，无法 mock 掉数据访问，必须启动真实数据库。

**来自参考项目的经验**

- **[A]** 的 `BaseRepository` 实现了通用 CRUD + 排序/过滤/分页，Service 只做业务编排。但 [A] 做了一个务实的妥协：`AsyncSession` 直接传入 Service 而不是封装在 Repository 里。原因是"我确定不会换 ORM，不需要为此多加一层抽象"。我们采纳这个决策——Session 传入 Repository，Service 可以在一个事务里组合多个 Repository 调用。
- **[B]** 没有 Repository 层，路由直接调 `crud.py`。这对小项目足够，但 [B] 自己也承认"modify CRUD utils in `./backend/app/crud.py`"——单文件 CRUD 在我们这个规模下会变成大泥球。
- **[C]** 明确建议"SQL-first, Pydantic-second"，意思是先写好 SQL 查询再包装成 Pydantic schema，而不是让 ORM 自动生成低效查询。Repository 层正好是放置优化过的 SQL 查询的地方。

**我们的决策**

引入 Repository，但不做过度抽象：
- Repository 直接接收 SQLAlchemy Session，不做额外封装
- Repository 只做数据访问，不做业务判断
- 通过 BaseRepository 提供通用 CRUD，避免每个 Repository 重写分页逻辑
- 不是所有服务都需要：`router_service` 无数据库，不引入

**不采纳的替代方案**

- ❌ 完整 Unit of Work 模式：增加大量样板代码，当前规模不需要
- ❌ Repository 返回 DTO 而非 ORM 对象：增加映射层，当前阶段收益不足

---

### 2. 为什么引入 Gateway 模式

**当前问题**

跨服务调用散落在各个 Service 内部：
- `user_service/services/admin_client.py` 直接 HTTP 调 admin-service
- `admin_service/services/identity_client.py` 调 user-service
- `router_service/services/identity_client.py` 调 user-service
- `testing_service/services/admin_identity_client.py` 调 admin-service

这些 `*_client.py` 存在几个问题：放在 `services/` 目录下容易和本地业务 service 混淆；没有接口契约，调用方直接依赖 HTTP 实现细节；错误处理和重试逻辑每个 client 各写一套。

**来自参考项目的经验**

- **[A]** 提出了 Gateway 模式，是整个 Starter Kit 最有价值的设计。它的核心思想是：模块对外只暴露一个 Gateway 接口（抽象类），内部实现可以是本地方法调用，也可以是 HTTP。引用 [A] 的原话："如果我们决定把模块拆成独立微服务，只需要实现一个新版本的 Gateway 做 HTTP 请求。其他模块完全无感，继续正常工作。" 这正好匹配我们的架构——当前是单仓多服务，未来可能拆分。
- **[B]** 没有跨服务通信的概念（单体应用），不适用。
- **[C]** 建议按域组织代码而非按文件类型，Gateway 是域边界上的自然产物。

**我们的决策**

每个服务新建 `gateway.py`，包含两部分：
1. 该服务暴露给其他服务的接口契约（抽象类）
2. 该服务调用其他服务的实现（从 `*_client.py` 迁移来）

**和 [A] 的差异**

[A] 的 Gateway 全部是同进程调用（模块化单体），我们的 Gateway 需要支持 HTTP+HMAC 跨进程调用（当前的 `common/internal.py` 机制）。所以我们的 Gateway 实现类是 `HttpXxxGateway`，保留了现有的 HMAC 签名逻辑。

---

### 3. 为什么拆分 Policy 层

**当前问题**

`user_service/dependencies.py` 的 `get_current_user` 同时做了三件事：token 解析、用户查询、状态检查。审计中发现 `status == 2`（pending）用户没被拦截，修复后虽然加了检查，但身份识别和权限判断仍然混在一起。不同接口可能需要不同级别的权限检查（比如 `/auth/me` 可能允许 pending 用户查看自己的状态，而 `/billing/balance` 必须要求激活用户），当前的一刀切设计无法灵活应对。

**来自参考项目的经验**

- **[A]** 提出了独立的 `policies/` 目录，用 FastAPI 的 `Depends` 实现权限检查。引用 [A] 的原话："我发现把 action access logic 和 action logic 分开非常有用。这个方法在中大型项目中效果很好，长期维护也更轻松。" Policy 函数可以用在路由的 `dependencies` 参数上，也可以在 Service 内部直接调用。
- **[B]** 的权限检查写在 `deps.py` 里，和 token 解析混在一起，和我们当前的问题一样。
- **[C]** 建议"dependencies 不仅仅是 DI，也适合做请求校验"，但没有把权限检查独立成层。

**我们的决策**

每个有权限需求的服务新建 `policies.py`：
- `dependencies.py` 只做身份识别："这个请求是谁"
- `policies.py` 做权限判断："这个人能不能做这件事"

这样不同接口可以选择不同的 policy：
```python
@router.get("/me")
def get_me(user = Depends(require_active_user)): ...

@router.post("/admin/users")
def create_user(admin = Depends(require_superadmin)): ...
```

---

### 4. 为什么用 SoftDeleteMixin 而非 status 字段

**当前问题**

API Key 审计发现 `DELETE /keys/{id}` 是物理删除，导致 `api_call_logs` 和 `usage_stats` 的外键被 `SET NULL`，丢失了 key 归属关系。需要改成软删除。

**设计选择：`deleted_at` vs `status=DELETED`**

- **[A]** 提供了 `SoftDeleteMixin`，使用 `deleted_at` 字段，并且让 `BaseRepository` 自动过滤已删除记录。这是最常见的做法。
- `status=DELETED` 的问题在于：status 字段已经在承载业务语义（ACTIVE/DISABLED/EXPIRED），加一个 DELETED 状态会让状态机变复杂。而且删除是一个正交维度——一个 key 在被删除前可能处于任何状态，删除后你还想知道它删除前是什么状态。`deleted_at` 是时间戳，天然记录了"何时删除"，status 字段保持原值记录了"删除前是什么状态"。

**我们的决策**

在 `common/db/base.py` 中追加 `SoftDeleteMixin`：
- `deleted_at: DateTime, nullable, indexed`
- `BaseRepository._base_query()` 自动加 `WHERE deleted_at IS NULL`
- 不新增 `STATUS_DELETED`，保留删除前的 status 值
- 提供 `soft_delete()` 和 `hard_delete()` 两个方法，不同场景选用

---

### 5. 为什么拆分 schemas.py 为目录

**当前问题**

`user_service/schemas.py` 单文件混装了认证、billing、API Key 的所有请求和响应，且用户端和管理端共用 schema，导致 `operator_id`、内部 `user_id`、`ip` 等字段泄露给普通用户。

**来自参考项目的经验**

- **[A]** 每个模块都有独立的 `schemas/` 目录，按功能拆分。
- **[B]** 模型和 schema 分别在 `models.py` 和路由文件里用 SQLModel 统一处理。但 [B] 是单体小项目，这种方式在多模块场景下不够灵活。
- **[C]** 明确建议"按域组织而非按文件类型"，schema 应该跟着域走而不是全局一个大文件。

**我们的决策**

每个服务的 `schemas.py` 拆为 `schemas/` 目录：
```
schemas/
├── auth.py              # 认证相关请求和响应
├── billing.py           # 用户端 billing 响应（默认安全，不含内部字段）
├── billing_admin.py     # 管理端 billing 响应（继承用户端，追加内部字段）
├── keys.py              # API Key 请求和响应
└── common.py            # 公共 schema
```

关键规则：**用户端 schema 从零定义只含业务字段，管理端 schema 继承用户端再追加内部字段**。这样默认是安全的——新增字段时不会意外泄露，只有显式继承到 admin schema 的字段才对管理员可见。

---

### 6. 为什么引入统一的 ListParams 和 PaginatedResult

**当前问题**

billing/usage、billing/logs、keys 列表接口各自实现分页、排序、时间范围过滤。审计中发现 `/billing/usage/logs` 默认不带时间条件会全表 count，`/billing/usage` 没有最大时间跨度限制。每次修复都是在具体接口上打补丁，没有统一方案。

**来自参考项目的经验**

- **[A]** 提供了 `ListParams`（含 `SortParam`、`FilterParam`）和 `PaginatedResult`，配合 `ListParamsBuilder` 作为 FastAPI 依赖注入。新增一个列表接口只需要定义"允许哪些字段排序和过滤"，分页/排序/计数逻辑自动继承。
- **[C]** 建议"Decouple & Reuse dependencies"，分页参数就是一个典型的可复用依赖。

**我们的决策**

在 `common/db/query.py` 中提供 `ListParams` 和 `PaginatedResult`：
- `ListParams` 包含 `page`、`page_size`、`order_by`、`order_dir`、`time_field`、`start`、`end`、`max_span_days`
- `validate_time_range()` 方法：超出 `max_span_days` 拒绝；未传时间范围默认最近 30 天
- `BaseRepository.get_list(params, extra_filters)` 接受 `ListParams` 和业务层追加的过滤条件

**和 [A] 的差异**

[A] 的 `ListParamsBuilder` 是一个 FastAPI Depends 工厂，支持从 query string 自动解析。我们简化为 dataclass，在 endpoint 里手动构造。原因是我们的列表接口参数差异较大（有些按 api_key_id 过滤，有些按 model_name 过滤），统一解析器的泛化成本高于手动构造。

---

### 7. 为什么引入 LifecycleManager

**当前问题**

审计中发现 `InvitationReleaseOutbox` 的消费端在 `jobs.py` 中定义，但"生产上需要确保 user-service worker 进程实际运行"。SMTP 初始化、outbox 消费者、benchmark worker 各自在不同地方启动，没有统一的检查点。

**来自参考项目的经验**

- **[A]** 没有显式的生命周期管理（留给 Docker 处理）。
- **[B]** 有 `backend_pre_start.py` 做预检查，但只是脚本级别。
- FastAPI 本身提供了 `lifespan` 上下文管理器，是官方推荐的启动/关闭钩子机制。

**我们的决策**

在 `backend_app/lifecycle.py` 中提供 `LifecycleManager`，各服务注册自己的初始化和清理逻辑。好处是：
- 启动时可以确认所有组件都初始化了
- 关闭时按逆序清理，避免资源泄漏
- 新增组件只需要 `lifecycle.on_startup(init_xxx)`，不需要改 main.py 的核心逻辑

---

### 8. 为什么合并 testing_service 的 benchmark/ 和 benchmarking/

**当前问题**

`testing_service` 下有两个目录处理基准测试相关功能：
- `benchmark/`：engine、jobs、probe_runner、queue、tasks
- `benchmarking/`：schemas、services

两个目录名几乎同义，职责边界不清晰。

**来自参考项目的经验**

- **[C]** 明确建议"the best structure is one that is consistent, straightforward, and free of surprises"。两个几乎同名的目录是典型的"surprise"。
- **[A]** 的每个模块内部结构统一：routes/schemas/services/models，没有同义目录并存。

**我们的决策**

合并为单一的 `benchmark/` 目录，把 `benchmarking/schemas.py` 和 `benchmarking/services.py` 移入 `benchmark/`。

---

### 9. 为什么不做某些改造

**不改 sync 为 async SQLAlchemy**

- **[A]** 全量使用 async SQLAlchemy + psycopg3。
- **[C]** 明确警告："如果路由定义为 async，它会通过 await 调用，FastAPI 信任你只做非阻塞 I/O。如果你在 async 路由里执行阻塞操作，event loop 会被卡住。"
- 我们当前所有数据访问都是 sync 的，切换到 async 意味着改写所有 Service 和 Repository，加 `await` 关键字，测试也要全部改。这是一个高风险低收益的变更——当前性能没有因为 sync 而成为瓶颈。

**不引入第三方 DI 容器**

- **[A]** 明确说："使用 python-dependency-injector 可以让一些方案更优雅，但为了简单和一致性，我决定使用 FastAPI 内置的 DI 能力。"
- 我们采纳同样的决策。FastAPI 的 `Depends` 已经足够处理 Repository、Service、Gateway 的注入。

**不引入事件总线**

- **[A]** 集成了 `fastapi-events` 做模块间异步通信，有 Event 和 Listener 的完整机制。
- 我们当前只有一个异步通信场景（邀请码释放），已经通过 Outbox 解决了。引入事件总线会增加复杂度（事件定义、监听器注册、分发器配置），在没有更多场景之前不值得。等到有 3 个以上异步通信场景时再考虑。

**不引入 DDD 四层架构**

- 搜索中发现的 `onlythompson/fastapi-microservice-template` 采用了 domain/application/infrastructure/presentation 四层。但这种架构适合业务逻辑极其复杂、需要严格隔离领域概念的场景。我们的复杂度集中在数据一致性和并发安全，而不是领域建模。Repository + Service 两层足够。

---

## 第二部分：全项目目标结构

### 目录总览

```text
backend/
├── src/
│   ├── backend_app/
│   │   ├── config.py
│   │   ├── main.py                     # 改造：接入 LifecycleManager
│   │   └── lifecycle.py                # 新增
│   │
│   ├── common/
│   │   ├── config.py                   # 不变
│   │   ├── health.py                   # 不变
│   │   ├── internal.py                 # 不变（HMAC 机制继续使用）
│   │   ├── observability.py            # 不变
│   │   ├── core/
│   │   │   ├── exception_handlers.py   # 不变
│   │   │   └── exceptions.py           # 不变
│   │   ├── db/
│   │   │   ├── base.py                 # 改造：追加 SoftDeleteMixin + 索引命名约定
│   │   │   ├── runtime.py              # 不变
│   │   │   ├── repository.py           # 新增：BaseRepository
│   │   │   └── query.py                # 新增：ListParams, PaginatedResult
│   │   ├── gateway/                    # 新增
│   │   │   └── base.py
│   │   ├── api/                        # 新增
│   │   │   └── pagination.py           # 统一分页响应 schema
│   │   ├── models/                     # 不变
│   │   ├── services/                   # 不变
│   │   │   ├── content/
│   │   │   └── identity/
│   │   └── utils/                      # 不变
│   │       ├── crypto.py / jwt.py / openai_compat.py
│   │       ├── password.py / snowflake.py / timezone.py
│   │
│   ├── admin_service/
│   │   ├── main.py / config.py / db.py          # 不变
│   │   ├── dependencies.py                      # 不变
│   │   ├── policies.py                          # 新增
│   │   ├── gateway.py                           # 新增（替代 identity_client.py）
│   │   ├── exceptions.py / bootstrap_superadmin.py  # 不变
│   │   ├── api/v1/                              # 不变
│   │   │   ├── router.py
│   │   │   └── endpoints/ (auth, invitation, admin_users, admin_audit_logs, internal)
│   │   ├── schemas/                             # 拆分自 schemas.py
│   │   │   ├── auth.py
│   │   │   ├── invitation.py
│   │   │   ├── admin_user.py
│   │   │   └── audit_log.py
│   │   ├── models/                              # 不变
│   │   │   ├── admin_user.py / invitation_code.py / admin_audit_log.py
│   │   ├── repositories/                        # 新增
│   │   │   ├── admin_user_repository.py
│   │   │   ├── invitation_repository.py
│   │   │   └── audit_log_repository.py
│   │   ├── services/                            # 精简（SQL 下沉到 repository）
│   │   │   ├── auth_service.py / invitation_service.py
│   │   │   ├── management_service.py / audit_service.py
│   │   │   └── bootstrap_service.py
│   │   │   # identity_client.py → 迁移到 gateway.py 后删除
│   │   └── utils/password.py                    # 不变
│   │
│   ├── user_service/
│   │   ├── config.py / db.py                    # 不变
│   │   ├── dependencies.py                      # 精简：只做身份识别
│   │   ├── policies.py                          # 新增
│   │   ├── gateway.py                           # 新增（替代 admin_client.py + 对外暴露）
│   │   ├── jobs.py / worker.py                  # 不变
│   │   ├── api/v1/                              # 不变
│   │   │   ├── router.py
│   │   │   └── endpoints/ (auth, internal, billing, admin_billing, keys)
│   │   ├── schemas/                             # 拆分自 schemas.py
│   │   │   ├── auth.py
│   │   │   ├── billing.py          # 用户端（默认安全）
│   │   │   ├── billing_admin.py    # 管理端（继承扩展）
│   │   │   ├── keys.py
│   │   │   └── common.py
│   │   ├── models/                              # 微调
│   │   │   ├── user.py / user_session.py / email_verification_code.py
│   │   │   ├── user_api_key.py     # 混入 SoftDeleteMixin
│   │   │   ├── balance_transaction.py / topup_order.py
│   │   │   ├── api_call_log.py / usage_stat.py
│   │   │   └── invitation_release_outbox.py
│   │   ├── repositories/                        # 新增
│   │   │   ├── user_repository.py
│   │   │   ├── session_repository.py
│   │   │   ├── email_code_repository.py
│   │   │   ├── api_key_repository.py
│   │   │   ├── balance_tx_repository.py
│   │   │   ├── topup_order_repository.py
│   │   │   └── usage_stat_repository.py
│   │   ├── services/                            # 精简
│   │   │   ├── auth_service.py / email_service.py
│   │   │   ├── api_key_service.py / balance_service.py
│   │   │   ├── topup_order_service.py / usage_stat_service.py
│   │   │   # admin_client.py → 迁移到 gateway.py 后删除
│   │   └── utils/                               # 不变
│   │       ├── password.py / email.py / api_key_policy.py
│   │
│   ├── testing_service/
│   │   ├── main.py / config.py / db.py          # 不变
│   │   ├── dependencies.py                      # 不变
│   │   ├── gateway.py                           # 新增（替代 admin_identity_client.py）
│   │   ├── schemas/                             # 拆分自 schemas.py
│   │   │   ├── model.py / provider.py / benchmark.py / vendor.py
│   │   ├── api/v1/                              # 不变
│   │   │   ├── router.py
│   │   │   └── endpoints/ (models, providers, vendors, model_providers, benchmark, internal_router)
│   │   ├── benchmark/                           # 合并 benchmark/ + benchmarking/
│   │   │   ├── engine.py / jobs.py / probe_runner.py / queue.py / tasks.py
│   │   │   ├── schemas.py      # 从 benchmarking/ 合入
│   │   │   └── services.py     # 从 benchmarking/ 合入
│   │   ├── catalog/ / core/ / provider_config/  # 不变
│   │   ├── models/                              # 不变
│   │   ├── repositories/                        # 新增
│   │   │   ├── model_repository.py
│   │   │   └── benchmark_repository.py
│   │   ├── services/                            # 精简
│   │   │   ├── model_service.py / benchmark_job_service.py
│   │   │   # admin_identity_client.py → 迁移到 gateway.py 后删除
│   │   └── worker.py                            # 不变
│   │
│   └── router_service/
│       ├── main.py / config.py / dependencies.py / logging.py  # 不变
│       ├── gateway.py                           # 新增（替代 identity_client.py）
│       ├── schemas/                             # 拆分自 schemas.py
│       │   ├── chat.py / completions.py / meta.py
│       ├── routers/                             # 不变
│       │   ├── chat.py / completions.py / meta.py
│       ├── nn/                                  # 不变
│       │   ├── cg_tabm.py / probe.py
│       ├── services/                            # 精简
│       │   ├── router_engine.py / upstream.py
│       │   # identity_client.py → 迁移到 gateway.py 后删除
│       └── utils/                               # 不变
│           ├── input_builder.py / runtime_config.py / scoring.py / text.py
│
├── migrations/                                  # 不变，追加新迁移
├── tests/                                       # 渐进重组（见第四部分）
├── scripts/ / deploy/ / docs/                   # 不变
└── pyproject.toml
```

---

## 第三部分：分层规则与代码示例

### 架构分层图

```
┌─────────────────────────────────────────────────┐
│  Endpoints (api/v1/endpoints/)                   │
│  职责：入参解析、响应组装、cookie 操作             │
│  规则：不包含业务逻辑，不直接访问 DB              │
│  来源：[B] 的路由层 + [C] 的"thin controller"建议 │
├─────────────────────────────────────────────────┤
│  Policies (policies.py)                          │
│  职责：判断"当前用户能否执行此操作"               │
│  规则：通过 Depends 注入，独立于 Service          │
│  来源：[A] 的 policies/ 目录                     │
├─────────────────────────────────────────────────┤
│  Services (services/)                            │
│  职责：业务逻辑编排，事务边界控制                  │
│  规则：调用 Repository 做数据访问，不直接拼 SQL   │
│  规则：调用其他服务通过 Gateway，不直接 import    │
│  来源：三个项目共识                              │
├─────────────────────────────────────────────────┤
│  Repositories (repositories/)                    │
│  职责：数据访问，SQL 查询，行锁，幂等检查         │
│  规则：只做数据操作，不做业务判断                  │
│  规则：继承 BaseRepository 获得通用 CRUD          │
│  来源：[A] 的 BaseRepository                     │
├─────────────────────────────────────────────────┤
│  Models (models/)                                │
│  职责：表结构定义，字段约束                       │
│  规则：继承 BaseModel，按需混入 SoftDeleteMixin   │
│  来源：[A] 的 SoftDeleteMixin + 项目现有 base.py  │
├─────────────────────────────────────────────────┤
│  Schemas (schemas/)                              │
│  职责：输入校验、输出序列化                       │
│  规则：用户端/管理端拆分，管理端继承用户端        │
│  来源：[C] 的按域组织 + 审计中发现的字段泄露问题  │
└─────────────────────────────────────────────────┘
```

### Service + Repository 协作示例

```python
# ── Repository 层：只回答"数据在哪里、怎么取" ──

class BalanceTxRepository(BaseRepository[BalanceTransaction]):
    def find_by_idempotency_key(self, tx_type, ref_type, ref_id):
        """幂等检查：同一笔业务是否已入账"""
        return self.find_one(
            BalanceTransaction.type == tx_type,
            BalanceTransaction.ref_type == ref_type,
            BalanceTransaction.ref_id == ref_id,
        )

# ── Service 层：只回答"业务上该怎么做" ──

class BalanceService:
    def __init__(self, db):
        self._user_repo = UserRepository(db)
        self._tx_repo = BalanceTxRepository(db)

    def freeze(self, user_id, amount, ref_type, ref_id):
        # 幂等（数据访问 → Repository）
        existing = self._tx_repo.find_by_idempotency_key("freeze", ref_type, ref_id)
        if existing:
            return existing

        # 锁行（数据访问 → Repository）
        user = self._user_repo.get_for_update(user_id)
        if not user:
            raise UserNotFoundException()

        # 余额判断（业务规则 → Service 职责）
        if user.balance - user.frozen_amount < amount:
            raise InsufficientBalanceException()

        # 执行变更（数据访问 → Repository）
        user.frozen_amount += amount
        self._tx_repo.add(BalanceTransaction(...))

        # 提交（事务边界 → Service 决定）
        self._tx_repo.commit()
```

### Gateway 使用示例

```python
# ── 定义接口契约 ──

class AdminGatewayInterface(ABC):
    @abstractmethod
    def redeem_invitation(self, code: str, email: str) -> bool: ...

# ── HTTP 实现（从 admin_client.py 迁移） ──

class HttpAdminGateway(AdminGatewayInterface, BaseGateway):
    def redeem_invitation(self, code, email):
        # 复用 common/internal.py 的 HMAC 签名机制
        ...

# ── Service 中使用 ──

class AuthService:
    def __init__(self, db, admin_gateway: AdminGatewayInterface):
        self._admin = admin_gateway

    def register(self, ...):
        # 通过 Gateway 调用，不关心是 HTTP 还是本地
        self._admin.redeem_invitation(code, email)
```

### Policy 使用示例

```python
# dependencies.py — 身份识别
def get_current_user(request, db) -> User:
    token = _extract_token(request)
    payload = decode_access_token(token)
    user = db.query(User).filter(User.id == payload["uid"]).first()
    if not user:
        raise UserNotFoundException()
    return user

# policies.py — 权限判断（可组合）
def require_active_user(user = Depends(get_current_user)) -> User:
    if user.status == 0:
        raise UserDisabledException()
    if user.status == 2:
        raise EmailNotVerifiedException()
    return user

# endpoint — 选择需要的 policy
@router.post("/change-password")
def change_password(user = Depends(require_active_user)): ...
```

---

## 第四部分：跨服务通信规则

### 通信方式决策

```
同步获取结果 → Gateway
  注册时核销邀请码、validate API key 时查用户状态
  来源：[A] 的 Gateway 模式

最终一致 → Outbox + 定时重试
  注册失败释放邀请码
  来源：当前 InvitationReleaseOutbox 已工作，保持

异步通知 → 事件（后续引入）
  注册成功后发欢迎邮件
  来源：[A] 的 Events 机制，但当前不引入
```

### 服务依赖图

```
                    ┌──────────────┐
                    │ backend_app  │ lifecycle 管理
                    └──────┬───────┘
            ┌──────────────┼──────────────┬──────────────┐
            ▼              ▼              ▼              ▼
    ┌──────────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐
    │admin_service │ │user_svc  │ │testing_svc │ │router_svc  │
    │              │ │          │ │            │ │            │
    │ gateway ◄────┼─┤ gateway  │ │ gateway ──►│ │ gateway    │
    │   (暴露)     │ │ (调admin)│ │ (调admin)  │ │  (调user)  │
    │              │ │          │ │            │ │     │      │
    │              ├─►gateway   │ │            │ │     ▼      │
    │              │ │ (暴露)   │ │            │ │ user gw    │
    └──────────────┘ └──────────┘ └────────────┘ └────────────┘

    所有服务 → import common.* ✅
    服务之间直接 import models/services ❌
```

### 模块导出规范

```python
# 每个服务的 __init__.py 显式声明对外暴露内容
# 其他服务只 import 这里列出的内容

# src/admin_service/__init__.py
from .gateway import AdminGatewayInterface
from .policies import require_superadmin, require_active_admin
__all__ = [...]

# src/user_service/__init__.py
from .gateway import UserGatewayInterface, AdminGatewayInterface
from .policies import require_active_user, require_email_verified
__all__ = [...]
```

---

## 第五部分：测试策略

### 测试目录重组

```text
tests/
├── common/                              # 基础设施测试
│   ├── test_base_repository.py          # CRUD、软删除过滤、分页、行锁
│   ├── test_list_params.py              # 时间范围校验、默认值
│   └── test_soft_delete_mixin.py
│
├── admin_service/                       # admin 服务测试
│   ├── test_policies.py
│   ├── test_invitation_repository.py
│   ├── test_auth_service.py
│   └── test_invitation_endpoints.py
│
├── user_service/                        # user 服务测试
│   ├── test_policies.py
│   ├── test_api_key_repository.py
│   ├── test_balance_service.py
│   ├── test_auth_endpoints.py
│   ├── test_billing_endpoints.py
│   └── test_keys_endpoints.py
│
├── testing_service/                     # testing 服务测试
│   ├── test_model_repository.py
│   └── test_benchmark_service.py
│
├── router_service/                      # router 服务测试
│   └── test_gateway.py
│
├── architecture/                        # 架构约束测试
│   ├── test_architecture_boundaries.py  # 从现有迁移
│   ├── test_internal_contracts.py
│   ├── test_schema_drift.py
│   ├── test_schema_ownership.py
│   ├── test_migration_structure.py
│   └── test_no_cross_service_import.py  # 新增：确保无跨服务直接 import
│
├── integration/                         # 跨服务集成测试
│   ├── test_register_flow.py            # user → admin 邀请码核销
│   └── test_api_call_flow.py            # router → user key 校验 → billing
│
├── test_*.py                            # 现有文件保留，逐步迁移
└── conftest.py
```

**迁移策略（来自 [C]）**：新测试直接放新目录。旧文件保留到新测试完全覆盖后再删除。不做一次性迁移。

### 测试命名规范

```python
# 格式：test_{被测行为}_{场景}_{预期结果}
# 来源：[C] 的"consistent naming"建议

def test_freeze_insufficient_balance_raises_exception(): ...
def test_topup_already_paid_order_rejects(): ...
def test_validate_by_hash_expired_key_raises_expired_exception(): ...
def test_change_password_revokes_all_sessions_in_same_commit(): ...
```

---

## 第六部分：执行顺序

### 阶段一：common 基础设施（3-5 天）

| 任务 | 文件 |
|------|------|
| SoftDeleteMixin + 索引命名约定 | `common/db/base.py` |
| BaseRepository | `common/db/repository.py` |
| ListParams + PaginatedResult | `common/db/query.py` |
| BaseGateway | `common/gateway/base.py` |
| PaginatedResponse | `common/api/pagination.py` |
| LifecycleManager | `backend_app/lifecycle.py` |
| 测试 | `tests/common/` |

**验收**：现有全部测试不变 + common 新增测试全绿。不改任何服务代码。

### 阶段二：user_service — API Key 试点（1 周）

| 任务 | 文件 |
|------|------|
| 混入 SoftDeleteMixin | `models/user_api_key.py` + Alembic 迁移 |
| Repository | `repositories/api_key_repository.py` |
| Service 精简 | `services/api_key_service.py` |
| Schema 拆分 | `schemas/keys.py` |
| Policy | `policies.py` |
| 测试 | `tests/user_service/test_api_key_repository.py` |

**为什么先做 API Key**：体量最小、正好有审计问题要修、可以完整验证 Repository + Policy + Schema 拆分 + SoftDeleteMixin 四个新模式。

### 阶段三：user_service — Billing + Auth（1-2 周）

| 任务 | 文件 |
|------|------|
| 6 个 Repository | `repositories/` 下各文件 |
| Service 精简 | 所有 service 改为调用 repository |
| Schema 全部拆分 | `schemas/` 目录替代 `schemas.py` |
| dependencies 精简 | `dependencies.py` → 身份识别 only |
| admin_client 迁移 | `gateway.py` 替代 `services/admin_client.py` |

**验收**：`admin_client.py` 删除 + 旧 `schemas.py` 删除 + 全量测试通过。

### 阶段四：admin_service（1 周）

| 任务 | 文件 |
|------|------|
| Schema 拆分 | `schemas/` |
| 3 个 Repository | `repositories/` |
| Gateway | `gateway.py` 替代 `services/identity_client.py` |
| Policy | `policies.py` |

### 阶段五：testing_service（3-5 天）

| 任务 | 文件 |
|------|------|
| 合并 benchmark/ + benchmarking/ | `benchmark/` |
| Schema 拆分 | `schemas/` |
| 2 个 Repository | `repositories/` |
| Gateway | `gateway.py` 替代 `services/admin_identity_client.py` |

### 阶段六：router_service + 收尾（3-5 天）

| 任务 | 文件 |
|------|------|
| Schema 拆分 | `schemas/` |
| Gateway | `gateway.py` 替代 `services/identity_client.py` |
| Lifecycle 接入 | `backend_app/main.py` |
| 架构测试 | `tests/architecture/test_no_cross_service_import.py` |
| 集成测试 | `tests/integration/` |

**最终验收**：
- 所有 `*_client.py` 已删除
- 所有旧 `schemas.py` 已删除
- 无跨服务直接 model/service import（架构测试保证）
- 全量测试通过

---

## 第七部分：重构安全网

```bash
# 每个阶段前后跑

# 1. 全量测试
uv --cache-dir /tmp/uv-cache run pytest tests/ -v

# 2. 各服务迁移
timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service user-service upgrade head
timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service admin-service upgrade head
timeout 30s uv --cache-dir /tmp/uv-cache run migrate --service testing-service upgrade head

# 3. 架构边界
uv --cache-dir /tmp/uv-cache run pytest tests/test_architecture_boundaries.py -v

# 4. Schema 一致性
uv --cache-dir /tmp/uv-cache run pytest tests/test_schema_drift.py tests/test_schema_ownership.py -v
```

红灯即停。不带着失败的测试进入下一阶段。