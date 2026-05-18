# Git 开发规范

## 一、分支策略

### 核心原则

- `main` 为生产分支，**禁止直接 push**，只接受 PR 合入
- `develop` 为日常集成分支，所有功能从此切出，完成后合回
- 功能分支生命周期短，合并后立即删除

### 分支流向

```
日常开发：develop → feat/xxx  → PR → develop
发布上线：develop             → PR → main（打 tag）
紧急修复：main    → hotfix/xxx → PR → main + develop
```

### 分支命名规范

| 前缀            | 用途                   | 示例                           |
| ------------- | ---------------------- | ------------------------------ |
| `feat/`       | 新功能开发             | `feat/user-login`              |
| `fix/`        | 非紧急 bug 修复        | `fix/order-calc-error`         |
| `hotfix/`     | 生产环境紧急修复       | `hotfix/payment-crash`         |
| `refactor/`   | 重构，不改变行为       | `refactor/auth-module`         |
| `perf/`       | 性能优化               | `perf/db-query-optimize`       |
| `test/`       | 补充测试               | `test/user-service-unit`       |
| `docs/`       | 文档变更               | `docs/api-readme`              |
| `chore/`      | 构建/依赖/配置等杂项   | `chore/upgrade-webpack`        |
| `ci/`         | CI/CD 流程变更         | `ci/add-lint-check`            |
| `revert/`     | 回滚某次提交           | `revert/feat-user-login`       |
| `release/`    | 发布准备               | `release/v1.2.0`               |
| `experiment/` | 实验性探索，不一定合入 | `experiment/new-render-engine` |

**命名约定：**
- 全小写，用 `-` 连字符，不用下划线
- 可携带 issue 编号：`feat/42-user-login`

---

## 二、Commit 规范

### 格式

```
<类型>(<scope>): <简短描述>
```

### 示例

```
feat(auth): 新增用户登录功能
fix(order): 修复金额计算精度问题
refactor(user): 拆分用户服务模块
docs: 更新 API 接口文档
chore: 升级 webpack 到 5.0
```

### 约定

- `scope` 可选，填模块名
- 描述用动词开头，不超过 50 字
- 类型与分支前缀保持一致

---

## 三、PR 规范

### PR 标题格式

与 commit 规范保持一致：

```
feat: 新增用户登录功能
fix: 修复订单金额计算错误
hotfix: 修复支付崩溃问题
refactor: 重构认证模块
docs: 补充 API 文档
```

### PR 目标分支

| 场景     | base 分支  |
| -------- | ---------- |
| 日常开发 | `develop`  |
| 发布上线 | `main`     |
| 紧急修复 | `main`     |

### 合并方式

统一使用 **Squash and merge**，将多个 commit 压成一个，保持主干历史干净。

---

## 四、完整开发流程

### 日常功能开发

```bash
# 1. 从 develop 切出功能分支
git checkout develop
git pull origin develop
git checkout -b feat/user-login

# 2. 开发并提交
git add .
git commit -m "feat(auth): 新增用户登录功能"

# 3. 推送到远端
git push origin feat/user-login

# 4. GitHub 上创建 PR
#    base: develop ← compare: feat/user-login

# 5. Review 通过后 Squash and merge

# 6. 合并后清理分支
git checkout develop
git pull origin develop
git branch -d feat/user-login
```

### 发布上线

```bash
# develop → PR → main
# 合并后打 tag

git checkout main
git pull origin main
git tag -a v1.0.0 -m "release: v1.0.0"
git push origin v1.0.0
```

### 紧急修复（hotfix）

```bash
# 1. 从 main 切出
git checkout main
git pull origin main
git checkout -b hotfix/payment-crash

# 2. 修复并提交
git commit -m "hotfix: 修复支付崩溃问题"

# 3. PR → main，合并后打 tag

# 4. 同步到 develop
git checkout develop
git cherry-pick <commit-hash>
git push origin develop
```

---

## 五、版本 Tag 规范

遵循语义化版本 `v<主版本>.<次版本>.<补丁>`：

| 场景           | 示例     |
| -------------- | -------- |
| 首次发布       | `v1.0.0` |
| 新增功能       | `v1.1.0` |
| bug 修复       | `v1.1.1` |
| 破坏性变更     | `v2.0.0` |

---

## 六、PR 模板

> 存放于 `.github/pull_request_template.md`

```markdown
## 改动说明

简述做了什么，为什么这么做

## 改动类型

- [ ] feat 新功能
- [ ] fix bug 修复
- [ ] hotfix 紧急修复
- [ ] refactor 重构
- [ ] perf 性能优化
- [ ] test 测试
- [ ] docs 文档
- [ ] chore 杂项
- [ ] ci CI/CD 变更
- [ ] revert 回滚

## 测试情况

- [ ] 本地自测通过
- [ ] 涉及的边界 case 已验证

## 相关 issue

closes #issue编号（如有）
```

---

## 七、分支保护配置

GitHub Settings → Branches → Add classic branch protection rule

```
Branch name pattern: main

✅ Require a pull request before merging
✅ Do not allow bypassing the above settings
```

## 用户标识规范

- 数据库内部数字 ID (`user_id: int`) **一律不传递给前端**，只在内部服务间使用
- 后端面向前端的响应 schema **禁止**包含 `user_id` 字段
- 前端 API 查询用户信息统一通过 `user_uid: str`（NanoID UID 字符串）
- 内部服务间通信（internal endpoints）可以使用数字 `user_id`
- 响应中需要标识用户时，使用 `user_uid: str` 字段
- 用户前端：通过 Bearer token 鉴权，无需传递用户标识

<!-- GSD:project-start source:PROJECT.md -->
## Project

**EucalAI Backend — Architecture Consolidation**

LLM API 中转平台后端，提供用户鉴权、API Key 管理、计费、模型路由、多协议转发（OpenAI/Anthropic/Responses）和管理后台功能。当前从 4 微服务合并为 2 服务（api-service + inference-service），消除不必要的跨服务 HTTP 调用。

**Core Value:** 用户通过 API Key 调用 LLM 转发端点时，请求必须低延迟、高可靠地完成鉴权→路由→转发→计费全链路。

### Constraints

- **部署**: api-service 必须适配 2h4g 服务器（4 workers × ~350MB ≈ 1.4GB + MySQL + Redis）
- **兼容性**: 前端 API 接口路径保持不变，仅改 host:port
- **零停机**: 需要并行运行验证后切换
- **技术栈**: Python 3.10+, FastAPI, SQLAlchemy 2.x async, Pydantic v2, Redis, ARQ
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Runtime
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12.x | Runtime | Already deployed. 3.12 has significant perf improvements (specializing interpreter, comprehension inlining). No reason to jump to 3.13 mid-refactor. |
| uvicorn | >=0.34.0 | ASGI server | Production-proven, `--workers N` for multi-process. Already in use. Pin to 0.34+ for HTTP/2 and improved shutdown. |
### Core Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | >=0.115.0 | HTTP framework | Already in use. 0.115+ has Pydantic v2 native, improved dependency injection perf, lifespan context. |
| Pydantic | >=2.5.0 | Validation/serialization | Already in use. v2 is 5-50x faster than v1 for model validation. Critical for relay request parsing. |
| pydantic-settings | >=2.1.0 | Configuration | Already in use. Supports `AliasChoices`, env file loading, nested models. |
| Starlette | (via FastAPI) | ASGI primitives | StreamingResponse for SSE relay, middleware, background tasks. Comes with FastAPI. |
### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLAlchemy | >=2.0.25 | ORM + async engine | Already in use. 2.0 async is mature. `create_async_engine` with connection pooling handles the merged workload. |
| aiomysql | >=0.2.0 | MySQL async driver | Already in use. Lightweight, stable. Alternative asyncmy has marginal perf gains but less ecosystem support. |
| MySQL 8.0 | 8.0.x | Primary database | Already deployed. Single `eucal_ai` database post-merge. |
| Alembic | >=1.14.0 | Schema migrations | Already in use. Single migration chain for merged database. |
### Caching & Queues
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Redis | >=5.0.0 (client) | Cache + rate limiting + pub/sub | Already in use. Three logical databases: db/0 (sessions/general), db/1 (ARQ queue), db/2 (routing config cache). |
| ARQ | >=0.26.0 | Background job queue | Already in use. Lightweight Redis-backed async task queue. Handles health checks, stats aggregation, email sending. |
### HTTP Client & LLM SDKs
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx | >=0.26.0 | Internal HTTP + inference-service calls | Already in use. Async, connection pooling, timeout control. Only remaining HTTP call is to inference-service. |
| openai | >=1.40.0 | OpenAI-compatible upstream calls | Already in use. Official SDK with streaming, retry, timeout. Used for Chat Completions + Responses protocol relay. |
| anthropic | >=0.34.0 | Anthropic upstream calls | Already in use. Official SDK with streaming. Used for Messages protocol relay. |
### Authentication & Security
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-jose[cryptography] | >=3.3.1 | JWT encode/decode | Already in use. Supports RS256/HS256. Handles user + admin token types. |
| passlib[bcrypt] | >=1.7.4 | Password hashing | Already in use. Wraps bcrypt with `asyncio.to_thread()` for non-blocking hash. |
| bcrypt | >=3.2.0,<4.0.0 | Bcrypt backend | Pin <4.0 because passlib has compatibility issues with bcrypt 4.x API changes. |
| cryptography | >=42.0.0 | AES-256-GCM for pool account secrets | Already in use for encrypting provider API keys at rest. |
### Utilities
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| snowflake-id | >=1.0.0 | Distributed ID generation | Already in use. worker_id=1 (user tables), worker_id=2 (admin tables). No collision post-merge. |
| nanoid | >=2.0.0 | User-facing UIDs | Already in use. 10-char NanoID for external identifiers (user_uid, key prefix). |
| cachetools | >=5.0.0 | In-memory TTL cache | Already in use. `TTLCache` for API key validation cache (2048 entries, 60s TTL). |
| slowapi | >=0.1.9 | HTTP rate limiting | Already in use for admin/user endpoints. Relay uses custom Redis-based rate limiter. |
### Dev Tools
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ruff | latest | Linting + formatting | Already configured. Fast, replaces flake8+isort+black. |
| mypy | latest | Type checking | Already configured with `--strict` on router-service. |
| hatchling | latest | Build backend | Already in use. Simple, fast PEP 517 builds. |
| uv | latest | Package manager | Already in use. 10-100x faster than pip for resolution and install. |
## Key Architecture Decisions for Merged Stack
### Connection Pool Sizing (CRITICAL for 2h4g server)
# SQLAlchemy engine configuration for api-service
### Redis Connection Strategy
# Separate pools for different concerns
### Uvicorn Worker Configuration
### Streaming Relay Pattern
# Use Starlette StreamingResponse for SSE relay
### Fire-and-Forget DB Writes
# Replace CallLogBuffer HTTP batch with direct async DB write
# Non-blocking: doesn't hold up the response
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| ASGI Server | uvicorn (multi-worker) | gunicorn + uvicorn workers | Unnecessary complexity for 4 workers. uvicorn `--workers` is sufficient. gunicorn adds process management overhead with no benefit at this scale. |
| MySQL Driver | aiomysql | asyncmy | asyncmy claims better perf but has fewer users, less battle-tested. aiomysql is already working in production. Not worth the migration risk. |
| Task Queue | ARQ | Celery | Celery is overkill for this workload (health checks, stats). ARQ is async-native, Redis-backed, minimal overhead. Already in use. |
| JWT Library | python-jose | PyJWT | python-jose already in use, supports JWE if needed later. PyJWT is simpler but would require migration effort for zero benefit. |
| Rate Limiting | Custom Redis (relay) + slowapi (API) | redis-py-cluster rate limiting | Single Redis instance is sufficient at current scale. Custom implementation gives exact control over token bucket + sliding window semantics. |
| HTTP Client | httpx | aiohttp | httpx has better API, type hints, and is already in use. aiohttp would require rewriting all HTTP client code. |
| LLM Relay | openai + anthropic SDKs | litellm | litellm adds abstraction overhead and version churn. Direct SDK usage gives full control over streaming, error handling, and protocol-specific features. The existing router-service already uses direct SDKs for relay. |
| Config | pydantic-settings | dynaconf / python-decouple | pydantic-settings integrates natively with FastAPI's DI. Type-safe, validates at startup. Already in use. |
| ID Generation | snowflake-id | UUID v7 | Snowflake IDs already in production data. Switching would require data migration. Snowflake gives time-ordering + worker isolation. |
| Password Hashing | passlib + bcrypt<4 | argon2-cffi | bcrypt is industry standard, already in production. argon2 is theoretically better but requires tuning and passlib already wraps bcrypt well. |
## What NOT to Use
| Technology | Why Avoid |
|------------|-----------|
| litellm (for relay) | Adds 50+ MB of dependencies, version churn every week, abstracts away protocol details you need to control (streaming chunk format, error mapping, token counting). Use direct openai/anthropic SDKs. |
| Celery | Massive dependency tree, requires separate broker config, overkill for 3-4 background job types. ARQ is async-native and already working. |
| SQLModel | Thin wrapper over SQLAlchemy that adds confusion about which API to use. Pure SQLAlchemy 2.0 is clearer and more powerful. |
| asyncmy | Marginal perf gain not worth the risk of switching MySQL drivers mid-refactor. |
| gunicorn | Adds process manager complexity. uvicorn `--workers` handles multi-process fine for 4 workers. |
| FastAPI-Cache | Adds decorator magic that's hard to invalidate precisely. Manual Redis cache with explicit invalidation (RoutingConfigCache pattern) is more predictable. |
| Dramatiq | Another task queue option but not async-native. ARQ is the right choice for async FastAPI. |
| bcrypt>=4.0.0 | Breaking API change that passlib hasn't fully adapted to. Pin <4.0 until passlib releases a compatible version or migrate to argon2. |
## Performance Configuration
### SQLAlchemy Session Strategy
# Use scoped sessions per-request via FastAPI dependency
### API Key Validation Cache
# In-process cache avoids DB hit on every relay request
### Routing Config Cache (Redis + DB)
# Two-tier cache: in-process dict (5s) -> Redis (60s) -> DB
# Admin writes invalidate Redis key, forcing reload on next request
## Installation
# Core dependencies (api-service pyproject.toml)
# Dev dependencies
## Confidence Assessment
| Area | Confidence | Reason |
|------|------------|--------|
| Core framework (FastAPI + SQLAlchemy + Pydantic) | HIGH | Already in production across all 4 services. Versions verified from installed packages. |
| Database (MySQL + aiomysql + Alembic) | HIGH | Already in production. Merge is additive (combine two DBs), no driver change. |
| Caching (Redis + cachetools) | HIGH | Already in production. RoutingConfigCache pattern is well-defined in architecture doc. |
| LLM SDKs (openai + anthropic) | HIGH | Already in production in router-service. Direct SDK usage is the right pattern for protocol relay. |
| Connection pool sizing | MEDIUM | Calculated from 2h4g constraints but needs load testing to validate. May need tuning. |
| bcrypt version pin | MEDIUM | passlib + bcrypt<4 compatibility is a known issue but the exact resolution timeline is unclear. Monitor for passlib updates. |
## Sources
- Installed package versions verified via `pip show` on the deployment environment (Python 3.12.3)
- Architecture decisions from `docs/architecture-refactoring.md` (project internal)
- Service patterns from existing CLAUDE.md files in admin-service, user-service, router-service
- SQLAlchemy 2.0 async patterns from existing `common/db/runtime.py` implementations
- Connection pool math: 4 workers x 15 connections = 60, within MySQL 8.0 default limit of 151
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| alipay-payment-integration | >- 支付宝开放平台支付产品接入最佳实践。涵盖当面付、订单码支付、App 支付、JSAPI 支付、手机网站支付、电脑网站支付、预授权支付、商家扣款等全场景产品选型与集成指导。 当用户提到"接入支付宝"、"集成支付宝支付"、"对接支付"、"支付宝收款"、"加个支付功能"、"支付宝下单"、"H5 支付"、"小程序支付"、"预授权"、"付款码"、"扫码支付"、"网页支付"、"PC 支付"、"周期扣款"、"自动续费"、"会员订阅"、"连续包月"、"代扣"时，或咨询支付产品相关报错、排查问题时使用此 Skill。 | `.agents/skills/alipay-payment-integration/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
