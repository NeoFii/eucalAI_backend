# Codebase Structure

**Analysis Date:** 2026-05-20

## Directory Layout

```
eucalAI_backend/
├── .agents/skills/              # Agent skill definitions (alipay-payment-integration)
├── .claude/                     # Claude Code config and skills
├── .github/                     # PR templates
├── .planning/                   # GSD workflow artifacts
│   ├── codebase/                # Codebase analysis docs (this file)
│   ├── phases/                  # Implementation phase plans (01-10)
│   ├── research/                # Research notes
│   └── todos/                   # Task tracking
├── docs/                        # Architecture and refactoring docs
├── gpu_stress_test/             # GPU benchmarking scripts
├── infra/                       # Infrastructure configs (systemd, nginx)
├── scripts/                     # Deployment/utility scripts
├── services/                    # All microservices
│   ├── api-service/             # Unified merged service (PRIMARY)
│   ├── admin-service/           # Legacy admin service
│   ├── user-service/            # Legacy user service
│   ├── router-service/          # Legacy relay service
│   └── inference-service/       # GPU inference service (standalone)
├── CLAUDE.md                    # Project instructions for Claude
├── DEPLOY.md                    # Deployment guide
└── README.md                    # Project overview
```

## api-service Internal Structure (Primary Service)

```
services/api-service/
├── api_service/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, lifespan, middleware, routes
│   ├── db.py                            # Legacy DB module (thin wrapper)
│   ├── common/                          # Shared infrastructure layer
│   │   ├── config.py                    # BaseServiceSettings (shared across services)
│   │   ├── health.py                    # Readiness probe builder
│   │   ├── internal.py                  # HMAC-signed internal HTTP client
│   │   ├── internal_logs.py             # Internal log ring buffer router
│   │   ├── observability.py             # Structured logging, middleware
│   │   ├── schemas.py                   # Shared Pydantic schemas
│   │   ├── api/
│   │   │   └── pagination.py            # ListParams, PaginatedResult
│   │   ├── core/
│   │   │   ├── exception_handlers.py    # Global exception → JSON response
│   │   │   └── exceptions.py            # Business exception hierarchy
│   │   ├── http/
│   │   │   ├── internal_auth.py         # HMAC receiver-side dependency
│   │   │   ├── internal_signing.py      # HMAC canonicalization primitives
│   │   │   └── request_context.py       # Request context (IP, UA)
│   │   ├── infra/
│   │   │   ├── cache.py                 # Redis db/2 pool (routing/token cache)
│   │   │   ├── redis.py                 # Redis db/0 pool (sessions)
│   │   │   └── db/
│   │   │       ├── _env_shared.py       # Alembic env helpers
│   │   │       ├── base.py              # DeclarativeBase + mixins
│   │   │       ├── query.py             # ListParams, PaginatedResult
│   │   │       ├── repository.py        # BaseRepository[ModelT]
│   │   │       ├── runtime.py           # ServiceDatabaseRuntime
│   │   │       └── schema_version.py    # Alembic head check
│   │   ├── security/
│   │   │   ├── crypto.py               # AES-256-GCM encrypt/decrypt
│   │   │   ├── jwt.py                  # JWT encode/decode
│   │   │   ├── password.py             # bcrypt hash/verify (async)
│   │   │   └── token_blacklist.py      # Token revocation
│   │   └── utils/
│   │       ├── api_key_policy.py        # Key generation policy
│   │       ├── email.py                 # Email utilities
│   │       ├── nanoid_uid.py            # NanoID generator
│   │       ├── password_policy.py       # Password strength rules
│   │       ├── snowflake.py             # Snowflake ID generator
│   │       └── timezone.py              # UTC+8 timezone helpers
│   ├── controllers/                     # HTTP endpoint layer
│   │   ├── __init__.py
│   │   ├── auth.py                      # /api/v1/auth/* (10 endpoints)
│   │   ├── billing.py                   # /api/v1/billing/* (8 endpoints)
│   │   ├── internal.py                  # /api/v1/internal/* (HMAC-protected)
│   │   ├── keys.py                      # /api/v1/keys/* (5 endpoints)
│   │   ├── model_catalog.py             # /api/v1/models/* (public catalog)
│   │   ├── admin/
│   │   │   ├── __init__.py              # Admin sub-router aggregator
│   │   │   ├── admin_users.py           # /admin/admins/*
│   │   │   ├── audit_logs.py            # /admin/audit-logs/*
│   │   │   ├── auth.py                  # /admin/auth/*
│   │   │   ├── dashboard.py             # /admin/dashboard/*
│   │   │   ├── model_catalog.py         # /admin/model-catalog/*
│   │   │   ├── pools.py                 # /admin/pools/*
│   │   │   ├── route_monitor.py         # /admin/route-monitor/*
│   │   │   ├── routing_settings.py      # /admin/routing-settings/*
│   │   │   ├── service_logs.py          # /admin/service-logs/*
│   │   │   ├── users.py                 # /admin/users/* (user management)
│   │   │   └── vouchers.py              # /admin/vouchers/*
│   │   └── relay/
│   │       ├── __init__.py              # Relay router aggregator
│   │       ├── anthropic.py             # POST /v1/messages
│   │       ├── chat.py                  # POST /v1/chat/completions
│   │       ├── models.py                # GET /v1/models
│   │       └── responses.py             # POST /v1/responses
│   ├── core/                            # Application bootstrap
│   │   ├── arq_pool.py                  # ARQ Redis pool (db/1)
│   │   ├── config.py                    # ApiServiceSettings (all config)
│   │   ├── db.py                        # DB engine/session module-level wrappers
│   │   ├── jobs.py                      # ARQ job definitions + cron schedule
│   │   ├── lifespan.py                  # LifespanRegistry + relay resource init
│   │   ├── policies.py                  # Auth policy dependencies
│   │   ├── router.py                    # Top-level APIRouter assembly
│   │   ├── worker.py                    # ARQ WorkerSettings entrypoint
│   │   └── dependencies/
│   │       ├── __init__.py              # Exports get_current_user, get_current_admin
│   │       ├── admin.py                 # Admin JWT dependency
│   │       └── user.py                  # User JWT dependency
│   ├── models/                          # SQLAlchemy ORM models (19 classes)
│   │   ├── __init__.py                  # All model exports
│   │   ├── admin_audit_log.py
│   │   ├── admin_user.py
│   │   ├── api_call_log.py
│   │   ├── audit_action_definition.py
│   │   ├── balance_transaction.py
│   │   ├── email_verification_code.py
│   │   ├── enums.py                     # AdminRole, AdminStatus, PoolAccountStatus
│   │   ├── model_catalog.py             # ModelVendor, ModelCategory, ModelCatalog, CategoryMap
│   │   ├── pool.py                      # Pool, PoolModelConfig, PoolAccount
│   │   ├── routing_setting.py
│   │   ├── topup_order.py
│   │   ├── usage_stat.py
│   │   ├── user.py
│   │   ├── user_api_key.py
│   │   ├── user_session.py
│   │   └── voucher_redemption_code.py
│   ├── relay/                           # LLM relay pipeline
│   │   ├── __init__.py
│   │   ├── auth.py                      # 3-tier API key validation
│   │   ├── billing.py                   # Pre-consume / settle / refund
│   │   ├── call_log_writer.py           # Fire-and-forget DB log writes
│   │   ├── channel_affinity.py          # Sticky channel routing (Redis)
│   │   ├── channel_selector.py          # Weighted channel selection + cooldown
│   │   ├── config_cache.py              # RoutingConfigCache singleton
│   │   ├── dependencies.py              # Relay singleton getters
│   │   ├── inference_client.py          # HTTP client to inference-service
│   │   ├── rate_limiter.py              # Redis sliding-window rate limiter
│   │   ├── retry_policy.py              # Upstream retry configuration
│   │   ├── routing.py                   # route_and_resolve() orchestration
│   │   ├── runtime_config.py            # normalize_runtime_config()
│   │   ├── sdk_clients.py              # SdkClientPool (OpenAI/Anthropic SDK instances)
│   │   ├── upstream.py                  # resolve_model_channel_target / provider_target
│   │   ├── upstream_dispatch.py         # dispatch() → correct SDK backend
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── anthropic_convert.py     # OpenAI→Anthropic message conversion
│   │   │   ├── anthropic_messages.py    # Anthropic Messages adapter
│   │   │   ├── openai_chat.py           # OpenAI Chat adapter
│   │   │   ├── openai_responses.py      # OpenAI Responses adapter
│   │   │   ├── protocol.py             # ProtocolAdapter + StreamConverter interfaces
│   │   │   └── responses_convert.py     # Responses API conversion
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   ├── anthropic_backend.py     # Anthropic SDK call wrappers
│   │   │   └── openai_backend.py        # OpenAI SDK call wrappers
│   │   ├── lifecycle/
│   │   │   ├── __init__.py              # Exports CallLifecycle
│   │   │   ├── finalize.py             # Stream finalization + billing settle
│   │   │   ├── orchestrator.py          # CallLifecycle class
│   │   │   └── stream.py               # SSE stream generators
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── anthropic.py             # Anthropic request/response schemas
│   │       ├── chat.py                  # ChatCompletionRequest schema
│   │       └── responses.py             # Responses API schemas
│   ├── repositories/                    # Data access layer
│   │   ├── __init__.py
│   │   ├── admin_user_repository.py
│   │   ├── api_key_repository.py
│   │   ├── audit_log_repository.py
│   │   ├── billing_repository.py
│   │   ├── call_log_repository.py
│   │   ├── model_catalog_repository.py
│   │   ├── pool_repository.py
│   │   ├── routing_setting_repository.py
│   │   ├── user_repository.py
│   │   └── voucher_repository.py
│   ├── schemas/                         # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── auth.py                      # User auth schemas
│   │   ├── billing.py                   # Billing schemas
│   │   ├── common.py                    # Shared schema types
│   │   ├── keys.py                      # API key schemas
│   │   ├── model_catalog.py             # Public model catalog schemas
│   │   └── admin/
│   │       ├── __init__.py
│   │       ├── admin_user.py
│   │       ├── audit_log.py
│   │       ├── auth.py
│   │       ├── model_catalog.py
│   │       ├── pool.py
│   │       ├── route_monitor.py
│   │       ├── routing_setting.py
│   │       ├── service_logs.py
│   │       ├── user_management.py
│   │       └── voucher.py
│   └── services/                        # Business logic layer
│       ├── __init__.py
│       ├── api_key_service.py
│       ├── auth_service.py
│       ├── balance_service.py
│       ├── email_service.py
│       ├── model_catalog_service.py
│       ├── topup_order_service.py
│       ├── usage_stat_service.py
│       ├── voucher_service.py
│       └── admin/
│           ├── __init__.py
│           ├── account_service.py
│           ├── admin_user_service.py
│           ├── audit_service.py
│           ├── auth_service.py
│           ├── bootstrap_service.py
│           ├── dashboard_service.py
│           ├── health_check_service.py
│           ├── model_catalog_service.py
│           ├── pool_service.py
│           ├── route_monitor_service.py
│           ├── routing_setting_service.py
│           ├── service_logs_service.py
│           └── voucher_service.py
├── migrations/
│   ├── env.py                           # Alembic environment
│   └── versions/
│       ├── __init__.py
│       └── 20260519_baseline.py         # Single baseline migration
├── tests/                               # Test suite
│   ├── __init__.py
│   ├── conftest.py                      # Root fixtures
│   ├── integration/                     # Integration tests (DB + Redis)
│   │   ├── conftest.py
│   │   ├── test_admin_relay_cache.py
│   │   ├── test_relay_e2e.py
│   │   └── test_resource_concurrency.py
│   ├── relay/                           # Relay-specific unit tests
│   │   ├── conftest.py
│   │   ├── test_anthropic_endpoint.py
│   │   ├── test_chat_endpoint.py
│   │   ├── test_models_endpoint.py
│   │   ├── test_rate_limiter.py
│   │   ├── test_responses_endpoint.py
│   │   ├── test_sdk_clients.py
│   │   └── test_streaming.py
│   └── test_*.py                        # Unit tests (40+ files)
└── pyproject.toml                       # Package config (hatchling)
```

## inference-service Internal Structure

```
services/inference-service/
├── config/                              # Runtime config + model paths JSON
├── src/
│   ├── common/                          # Shared infra (same pattern as api-service)
│   │   ├── config.py
│   │   ├── core/exceptions.py
│   │   ├── gateway/base.py
│   │   ├── internal.py
│   │   ├── internal_logs.py
│   │   └── observability.py
│   └── inference_service/
│       ├── __init__.py
│       ├── main.py                      # FastAPI app + CLI
│       ├── controllers/
│       │   └── classify.py              # POST /internal/v1/classify
│       ├── core/
│       │   ├── config.py                # InferenceSettings
│       │   ├── dependencies.py          # DI: get_engine, get_config_manager
│       │   ├── exceptions.py            # Inference-specific errors
│       │   └── router.py               # API router
│       ├── gateways/
│       │   ├── admin_config.py          # Legacy: fetch config from admin-service
│       │   └── api_service_config.py    # Fetch config from api-service /internal/*
│       ├── nn/
│       │   └── cg_tabm.py              # CG-TabM neural network model
│       ├── schemas/
│       │   └── classify.py              # ClassifyRequest/Response
│       ├── services/
│       │   ├── classify_service.py      # Orchestrates engine + config
│       │   ├── config_manager.py        # 3-tier config: api-service → cached → local
│       │   └── router_engine.py         # HybridIntegratedDifficultyRouter (ML core)
│       └── utils/
│           ├── input_builder.py         # Feature extraction from messages
│           ├── runtime_config.py        # Config normalization
│           ├── scoring.py              # Score band calculation
│           └── text.py                 # Text preprocessing
├── scripts/
│   ├── check_env.py
│   └── runtime_probe.py
└── pyproject.toml
```

## Legacy Services (Being Merged)

### user-service
```
services/user-service/src/
├── common/                  # Shared infra (duplicated pattern)
├── controllers/             # 12 controller files (auth, billing, keys, internal_*)
├── core/                    # config, db, dependencies, jobs, worker
├── gateways/                # model_catalog, system_settings (calls admin-service)
├── models/                  # 9 ORM models (user domain)
├── repositories/            # 9 repository classes
├── schemas/                 # 13 schema files
├── services/                # 11 service classes
└── utils/                   # api_key_policy, email, password
```

### admin-service
```
services/admin-service/src/
├── common/                  # Shared infra (duplicated pattern)
├── controllers/             # 12 controller files (auth, pools, routing, etc.)
├── core/                    # config, db, dependencies, jobs, worker, bootstrap
├── gateways/                # route_monitor, service_logs, user_management (calls user-service)
├── models/                  # 6 ORM models (admin domain)
├── repositories/            # 5 repository classes
├── schemas/                 # 11 schema files
├── services/                # 8 service classes
└── utils/                   # audit, parsing, password
```

### router-service
```
services/router-service/src/
├── common/                  # Shared infra (minimal — no DB)
├── controllers/             # chat, messages, responses, meta
├── core/                    # config, dependencies, router
├── gateways/                # admin_config, calllog, calllog_batch, user_identity
├── schemas/                 # anthropic, requests, responses
├── services/                # 15 service files (relay pipeline)
│   ├── adapters/            # openai_chat, anthropic_messages, openai_responses
│   └── lua/                 # Redis Lua scripts
└── utils/                   # billing, logging_config, runtime_config, text
```

## Key File Locations

**Entry Points:**
- `services/api-service/api_service/main.py`: HTTP server
- `services/api-service/api_service/core/worker.py`: ARQ worker
- `services/inference-service/src/inference_service/main.py`: Inference HTTP server

**Configuration:**
- `services/api-service/api_service/core/config.py`: All api-service settings
- `services/inference-service/src/inference_service/core/config.py`: Inference settings
- `.env`: Environment variables (DO NOT read contents)

**Core Logic:**
- `services/api-service/api_service/relay/lifecycle/orchestrator.py`: Relay pipeline
- `services/api-service/api_service/relay/config_cache.py`: Routing config management
- `services/api-service/api_service/relay/auth.py`: API key validation hot path
- `services/inference-service/src/inference_service/services/router_engine.py`: ML routing

**Testing:**
- `services/api-service/tests/`: All tests (unit + integration + relay)
- `services/api-service/tests/conftest.py`: Root test fixtures

## Naming Conventions

**Files:**
- Controllers: `controllers/{domain}.py` or `controllers/admin/{domain}.py`
- Services: `services/{domain}_service.py` or `services/admin/{domain}_service.py`
- Repositories: `repositories/{domain}_repository.py`
- Models: `models/{domain}.py` (one file per table or related group)
- Schemas: `schemas/{domain}.py` or `schemas/admin/{domain}.py`
- Relay adapters: `relay/adapters/{protocol}_{type}.py`

**Directories:**
- Feature domains grouped by layer (controllers/, services/, models/)
- Admin sub-domain uses `admin/` subdirectory within controllers, services, schemas
- Relay pipeline isolated in `relay/` with sub-packages (adapters, backends, lifecycle, schemas)

## Where to Add New Code

**New User-Facing API Endpoint:**
- Controller: `services/api-service/api_service/controllers/{domain}.py`
- Schema: `services/api-service/api_service/schemas/{domain}.py`
- Service: `services/api-service/api_service/services/{domain}_service.py`
- Repository: `services/api-service/api_service/repositories/{domain}_repository.py`
- Register route: `services/api-service/api_service/core/router.py`
- Tests: `services/api-service/tests/test_{domain}.py`

**New Admin Endpoint:**
- Controller: `services/api-service/api_service/controllers/admin/{domain}.py`
- Schema: `services/api-service/api_service/schemas/admin/{domain}.py`
- Service: `services/api-service/api_service/services/admin/{domain}_service.py`
- Register route: `services/api-service/api_service/controllers/admin/__init__.py`
- Tests: `services/api-service/tests/test_admin_{domain}.py`

**New Relay Protocol:**
- Controller: `services/api-service/api_service/controllers/relay/{protocol}.py`
- Adapter: `services/api-service/api_service/relay/adapters/{protocol}_{type}.py`
- Schema: `services/api-service/api_service/relay/schemas/{protocol}.py`
- Register route: `services/api-service/api_service/controllers/relay/__init__.py`
- Tests: `services/api-service/tests/relay/test_{protocol}_endpoint.py`

**New ORM Model:**
- Model: `services/api-service/api_service/models/{domain}.py`
- Register in: `services/api-service/api_service/models/__init__.py`
- Migration: `services/api-service/migrations/versions/YYYYMMDD_{description}.py`

**New Background Job:**
- Job function: `services/api-service/api_service/core/jobs.py`
- Register in `get_worker_settings_kwargs()` functions list + cron_jobs list

**New Shared Utility:**
- Infrastructure: `services/api-service/api_service/common/infra/{module}.py`
- Security: `services/api-service/api_service/common/security/{module}.py`
- General utils: `services/api-service/api_service/common/utils/{module}.py`

## Special Directories

**`.planning/`:**
- Purpose: GSD workflow artifacts (phase plans, codebase analysis, todos)
- Generated: Yes (by Claude agents)
- Committed: Yes

**`services/api-service/migrations/`:**
- Purpose: Alembic database schema migrations
- Generated: Via `alembic revision --autogenerate`
- Committed: Yes

**`services/inference-service/config/`:**
- Purpose: Runtime routing config JSON + model paths JSON
- Generated: No (manually maintained)
- Committed: Yes

**`infra/`:**
- Purpose: systemd unit files, nginx configs
- Generated: No
- Committed: Yes

**`gpu_stress_test/`:**
- Purpose: GPU benchmarking scripts and results
- Generated: Results are generated
- Committed: Yes

---

*Structure analysis: 2026-05-20*
