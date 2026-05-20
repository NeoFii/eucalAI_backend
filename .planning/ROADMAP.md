# Roadmap: EucalAI Backend Architecture Consolidation

## Overview

Consolidate 4 microservices (admin-service, user-service, router-service, inference-service) into 2 (api-service + inference-service). The roadmap follows horizontal dependency layers: scaffold the new service, merge infrastructure, migrate domain logic in dependency order, integrate the relay hot path, update the inference client, then validate and deploy. Fine granularity splits each major layer into independently verifiable sub-phases.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Project Scaffold & Common Layer** - Directory structure, settings, common utilities, lifespan skeleton
- [x] **Phase 2: Database & Redis Infrastructure** - SQLAlchemy engine, Redis pools, Snowflake ID, Alembic baseline
- [x] **Phase 3: Models & Repositories Migration** - ORM models and repository layer from user-service + admin-service
- [x] **Phase 4: User Domain Controllers** - Auth, API Key, billing, model catalog endpoints (completed 2026-05-18)
- [x] **Phase 5: Admin Domain Controllers** - Admin auth, all management endpoints (direct service calls) (completed 2026-05-19)
- [x] **Phase 6: Relay Core** - Call lifecycle, API Key local auth, billing integration, config cache (completed 2026-05-19)
- [ ] **Phase 7: Protocol Adapters & Streaming** - OpenAI/Anthropic/Responses endpoints, SSE, rate limiting
- [x] **Phase 8: Inference Service Update** - Internal HMAC endpoints, inference-service URL repoint (completed 2026-05-19)
- [x] **Phase 9: Integration Testing** - End-to-end validation of all domains working together (completed 2026-05-20)
- [ ] **Phase 10: Production Cutover** - DB merge, deployment, frontend switch, old service teardown

## Phase Details

### Phase 1: Project Scaffold & Common Layer

**Goal**: api-service project exists with correct structure, shared utilities, and a running health endpoint
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-07, INFRA-08, INFRA-09
**Success Criteria** (what must be TRUE):

  1. `uvicorn api_service.main:app` starts without error and /health returns 200
  2. Common layer modules (observability, HMAC internal, exceptions, utils) importable from api-service
  3. Unified Settings class loads all config from environment variables
  4. Lifespan context manager skeleton exists (resource init/shutdown hooks wired)

**Plans**: 3 plans, 3 waves

Plans:

- [x] 01-01: Directory structure and pyproject.toml
- [x] 01-02: Common layer merge and Settings class
- [x] 01-03: Lifespan skeleton and health endpoint

### Phase 2: Database & Redis Infrastructure

**Goal**: api-service connects to the merged database and Redis with production-safe pool settings
**Depends on**: Phase 1
**Requirements**: INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):

  1. Single async SQLAlchemy engine connects to eucal_ai database with pool_size=5, max_overflow=10
  2. Three Redis logical DBs initialized (session/rate-limit, ARQ, cache)
  3. Snowflake ID generator produces unique IDs across 4 worker processes (verified by test)
  4. Alembic baseline migration covers all tables from both original databases
  5. Lifespan properly creates and disposes DB engine and Redis pools on shutdown

**Plans**: 3 plans, 2 waves

Plans:

- [x] 02-01: SQLAlchemy async engine and session factory
- [x] 02-02: Redis connection pools (3 logical DBs)
- [x] 02-03: Snowflake ID with per-worker safety
- [x] 02-04: Alembic init and baseline migration

### Phase 3: Models & Repositories Migration

**Goal**: All ORM models and repository classes are available in api-service, passing unit tests
**Depends on**: Phase 2
**Requirements**: USER-02, USER-03, ADMIN-02
**Success Criteria** (what must be TRUE):

  1. All ORM models from user-service and admin-service import without circular dependencies
  2. Repository classes execute basic CRUD operations against test database
  3. Auth dependency functions (get_current_user, get_current_admin) resolve correctly

**Plans**: 3 plans, 2 waves

Plans:

- [x] 03-01: ORM models consolidation
- [x] 03-02: Repository layer migration
- [x] 03-03: Auth dependencies (JWT cookie extraction)

### Phase 4: User Domain Controllers

**Goal**: All user-facing endpoints (auth, API keys, billing, models) work identically to current user-service
**Depends on**: Phase 3
**Requirements**: USER-01, USER-04, USER-05, USER-06
**Success Criteria** (what must be TRUE):

  1. User can register, login, logout, and refresh tokens via cookie-based JWT
  2. User can create/list/revoke API keys
  3. User can query balance, transaction history, and usage statistics
  4. Public model catalog endpoint returns available models
  5. Email service sends verification and password reset emails

**Plans**: 3 plans, 3 waves

Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Auth controllers + Wave 0 foundations (settings, utils, schemas/common.py, ARQ pool, worker scaffold, 9 auth + email tests)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-02-PLAN.md — API Key + Billing controllers (5 services, 13 endpoints, SELECT FOR UPDATE + ref_id idempotency, 8 tests)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-03-PLAN.md — Model catalog read service + cache + final router wiring (4 public endpoints, 3 tests)

### Phase 5: Admin Domain Controllers

**Goal**: All admin endpoints call service layer directly (no HTTP proxy) with full feature parity
**Depends on**: Phase 3
**Requirements**: ADMIN-01, ADMIN-03, ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07, ADMIN-08, ADMIN-09, ADMIN-10, ADMIN-11, ADMIN-12
**Success Criteria** (what must be TRUE):

  1. Admin can login/logout/refresh with separate admin JWT cookie
  2. User management, dashboard stats, redemption codes, route monitor, service logs all call service layer directly (zero HTTP proxy calls)
  3. Pool/Channel/Model Catalog/Routing Config CRUD endpoints work
  4. Audit log records admin operations
  5. Super-admin bootstrap initialization works on fresh deployment

**Plans**: 3 plans, 2 waves

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — Admin auth + super-admin bootstrap + D-04 schemas hoist + HMAC sender port + AdminAuditService foundation (ADMIN-01, ADMIN-12; gates 05-02/05-03)

**Wave 2** *(blocked on 05-01 completion; 05-02 and 05-03 run in parallel)*

- [x] 05-02-PLAN.md — Pool/Channel/Model Catalog/Routing Settings CRUD + Admin-on-admin accounts + Audit log queries + Health-check ARQ cron + D-05 (mc:* SCAN+DEL) + D-06 (routing_config:version INCR) (ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-08)
- [x] 05-03-PLAN.md — Proxy elimination: user management / dashboard / vouchers / route-monitor / service-logs services replacing 5 gateways; service-logs HMAC HTTP to inference only (D-03) (ADMIN-03, ADMIN-07, ADMIN-09, ADMIN-10, ADMIN-11)

### Phase 6: Relay Core

**Goal**: Relay hot path authenticates, checks balance, routes, and bills without any HTTP calls to other services
**Depends on**: Phase 4
**Requirements**: RELAY-05, RELAY-06, RELAY-07, RELAY-08, RELAY-09, RELAY-10, RELAY-13, RELAY-14
**Success Criteria** (what must be TRUE):

  1. API Key validation uses local DB + TTLCache (no HTTP call)
  2. Balance check queries DB directly before relay
  3. RoutingConfigCache loads from DB+Redis with 60s TTL, admin writes trigger invalidation
  4. Call log writes via asyncio.create_task directly to DB (no HTTP buffer)
  5. Channel selection with circuit breaker and retry logic works

**Plans**: 3 plans, 2 waves

Plans:

- [x] 06-01-PLAN.md — API Key local auth + RelayBillingService (RELAY-05, RELAY-06, RELAY-10)
- [x] 06-02-PLAN.md — RoutingConfigCache + runtime_config + upstream (RELAY-07, RELAY-08)
- [x] 06-03-PLAN.md — CallLog writer + ChannelSelector + InferenceClient + routing + lifespan (RELAY-09, RELAY-13, RELAY-14)

### Phase 7: Protocol Adapters & Streaming

**Goal**: All three protocol endpoints handle requests end-to-end with streaming support and rate limiting
**Depends on**: Phase 6
**Requirements**: RELAY-01, RELAY-02, RELAY-03, RELAY-04, RELAY-11, RELAY-12
**Success Criteria** (what must be TRUE):

  1. POST /v1/chat/completions returns valid OpenAI Chat response (streaming and non-streaming)
  2. POST /v1/anthropic/messages returns valid Anthropic Messages response
  3. POST /v1/responses returns valid OpenAI Responses response
  4. GET /v1/models returns model list consistent with user's available models
  5. Three-tier rate limiting (per-key, per-user, global) rejects excess requests with 429

**Plans**: 3 plans, 2 waves

Plans:
**Wave 1**

- [ ] 07-01-PLAN.md — SdkClientPool + Token Bucket 限流 + backends + dispatch + Protocol 定义 + schemas

**Wave 2** *(blocked on Wave 1 completion; 07-02 and 07-03 run in parallel)*

- [ ] 07-02-PLAN.md — CallLifecycle 编排器 + 三个 ProtocolAdapter + 流式处理 + 四个 relay 端点挂载
- [ ] 07-03-PLAN.md — 集成测试：四个端点 + SSE 格式 + 限流 429 验证








### Phase 8: Inference Service Update

**Goal**: inference-service successfully communicates with api-service via HMAC-signed internal endpoints
**Depends on**: Phase 6
**Requirements**: INTL-01, INTL-02
**Success Criteria** (what must be TRUE):

  1. /api/v1/internal/routing-config/* endpoints respond with valid HMAC signatures
  2. inference-service fetches routing config from api-service URL without errors

**Plans**: 2 plans, 2 waves

Plans:

- [x] 08-01-PLAN.md — Internal HMAC endpoint (resolve_for_internal + controller + router mount)
- [x] 08-02-PLAN.md — Inference-service gateway rename + API_SERVICE_URL config repoint

### Phase 9: Integration Testing

**Goal**: All domains verified working together in a staging-like environment with no regressions
**Depends on**: Phase 7, Phase 8
**Requirements**: DEPL-02
**Success Criteria** (what must be TRUE):

  1. Full relay flow (auth -> route -> forward -> bill -> log) completes end-to-end
  2. Admin operations that affect relay (config change -> cache invalidation -> new routing) propagate correctly
  3. api-service with 4 workers stays under 1.5GB memory on 2h4g server
  4. No Snowflake ID collisions under concurrent load

**Plans**: 3 plans, 2 waves

Plans:

- [x] 09-01: End-to-end relay flow tests
- [x] 09-02: Cross-domain integration tests (admin -> relay cache)
- [x] 09-03: Resource and concurrency validation

### Phase 10: Production Cutover

**Goal**: Production traffic served by new architecture with zero data loss and no functionality regression
**Depends on**: Phase 9
**Requirements**: DEPL-01, DEPL-03, DEPL-04
**Success Criteria** (what must be TRUE):

  1. Two databases merged into eucal_ai with verified row counts (zero data loss)
  2. Frontend API_URL switched to api-service, all user flows work
  3. Old services stopped, no functionality regression observed over 24h monitoring

**Plans**: 3 plans, 2 waves

Plans:

- [ ] 10-01: Database merge procedure and verification
- [ ] 10-02: Traffic cutover and old service teardown

## Progress

**Execution Order:**
Phases execute in numeric order. Phase 5 can parallel Phase 4 (both depend on Phase 3). Phase 8 can parallel Phase 7 (both depend on Phase 6).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Project Scaffold & Common Layer | 3/3 | Complete | 2026-05-18 |
| 2. Database & Redis Infrastructure | 4/4 | Complete | 2026-05-19 |
| 3. Models & Repositories Migration | 3/3 | Complete | 2026-05-19 |
| 4. User Domain Controllers | 3/3 | Complete   | 2026-05-18 |
| 5. Admin Domain Controllers | 3/3 | Complete   | 2026-05-19 |
| 6. Relay Core | 0/3 | Not started | - |
| 7. Protocol Adapters & Streaming | 0/3 | Not started | - |
| 8. Inference Service Update | 0/1 | Not started | - |
| 9. Integration Testing | 0/3 | Not started | - |
| 10. Production Cutover | 0/2 | Not started | - |
