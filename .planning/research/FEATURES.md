# Feature Landscape

**Domain:** LLM API Gateway / Relay Platform
**Researched:** 2026-05-18
**Context:** Service consolidation refactoring (4 services -> 2 services)
**Reference projects:** new-api (Calcium-Ion), one-api (songquanpeng), LiteLLM, Portkey

## Table Stakes

Features users expect from any LLM API relay platform. Missing = product feels incomplete or unusable.

| Feature | Why Expected | Complexity | EucalAI Status |
|---------|--------------|------------|----------------|
| OpenAI-compatible API endpoint | Industry standard interface, all clients expect it | Med | Exists (router-service) |
| Multi-provider support (OpenAI, Anthropic, etc.) | Core value prop of a relay | Med | Exists (3 adapters) |
| API Key management (create/revoke/list) | Users need credentials to access the relay | Low | Exists (user-service) |
| Token-based billing (per-request metering) | Operators need to monetize or control costs | Med | Exists (user-service) |
| Balance/quota system | Users need spending visibility and limits | Med | Exists (user-service) |
| Streaming support (SSE) | Most LLM use cases require streaming | Med | Exists (router-service) |
| Admin panel (user/channel management) | Operators need to manage the platform | Med | Exists (admin-service) |
| Channel/provider pool management | Operators need to configure upstream providers | Med | Exists (admin-service pools) |
| Model catalog (what's available to users) | Users need to know what models they can call | Low | Exists (admin-service) |
| Request logging (call logs) | Debugging, billing verification, compliance | Med | Exists (user-service) |
| Rate limiting (RPM/TPM) | Prevent abuse, protect upstream quotas | Med | Exists (router-service) |
| User registration/login | Self-service access | Low | Exists (user-service) |
| Error handling with upstream retry | Reliability expectation for a proxy | Med | Exists (router-service) |
| Channel health monitoring | Operators need to know when upstreams fail | Low | Exists (pool health check) |

## Differentiators

Features that set EucalAI apart from commodity relay platforms. Not universally expected, but provide competitive advantage.

| Feature | Value Proposition | Complexity | EucalAI Status |
|---------|-------------------|------------|----------------|
| ML-based intelligent routing (Qwen2.5-7B + CG-TabM) | Routes requests to optimal model tier based on query complexity | High | Exists (inference-service) |
| Multi-protocol native support (OpenAI Chat + Anthropic Messages + Responses API) | Not just OpenAI-compat wrapper; native protocol fidelity | Med | Exists (3 adapters) |
| Tiered routing with score bands | Cost optimization: simple queries go to cheaper models | Med | Exists (routing_settings) |
| Channel affinity (session stickiness) | Better conversation continuity for multi-turn | Low | Exists (router-service) |
| Weighted channel selection with cooldown | Sophisticated load balancing across providers | Med | Exists (channel_selector) |
| Granular admin audit trail | Full before/after snapshots, action categorization | Med | Exists (admin-service) |
| Voucher/redemption code system | Marketing and onboarding tool | Low | Exists (admin + user) |
| Real-time service log viewer (RingBuffer) | Live debugging without log aggregation infra | Low | Exists (common/internal_logs) |
| Per-key model restrictions + IP allowlist | Fine-grained access control per API key | Low | Exists (user-service) |
| Provider cost tracking (dual-sided billing) | Profit margin visibility for operators | Low | Exists (api_call_logs) |
| Route monitor with time-series aggregation | Operational visibility into routing decisions | Med | Exists (admin-service) |

## Anti-Features

Features to explicitly NOT build during this refactoring. Either out of scope, harmful to architecture, or better solved differently.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Multi-tenant / organization hierarchy | Adds massive complexity; current single-operator model is correct for this scale | Keep flat user model. Add org support only if paying customers demand it. |
| Plugin/extension system | Over-engineering for a 2-person team; new-api's plugin system adds maintenance burden | Keep features in-tree. Refactor to clean interfaces for future extraction. |
| Built-in web UI for end users (chat playground) | Scope creep; relay platforms should be API-first | Provide API docs. Let users bring their own UI (ChatGPT-Next-Web, LobeChat, etc.) |
| Distributed tracing (OpenTelemetry spans) | Current scale doesn't justify the complexity; already removed traceId/spanId from logs | Use requestId correlation. Add OTel only when operating 10+ service instances. |
| Automatic model discovery from upstream | Fragile (upstream APIs change), creates ghost models in catalog | Keep manual model catalog. Provide sync-models helper for pools (already exists). |
| User group/tier pricing multipliers | new-api's group system adds complexity; EucalAI's ML routing already handles cost optimization | Keep per-model pricing. The routing tier system IS the cost optimization. |
| Webhook/callback notifications | No current use case; adds delivery guarantee complexity | Poll-based or SSE for real-time needs. |
| Multi-database / database sharding | Single MySQL instance is fine for current scale (< 1M rows) | Optimize queries and indexes. Revisit at 10M+ rows. |
| Custom model aliases per user | Complexity for marginal benefit; new-api supports this but it creates confusion | Keep global model catalog. Users see what's available. |
| Image/audio/embedding relay | Different protocols, different billing models, different upstream behavior | Focus on text completion relay. Add modalities as separate feature work later. |
| Self-hosted inference (local models) | inference-service already handles the ML routing model; don't conflate with LLM serving | Keep inference-service focused on classification. LLM serving is upstream providers' job. |

## Feature Dependencies

```
Registration/Login ─────────────────────────────────────────────────────┐
    │                                                                    │
    ▼                                                                    │
API Key Management ──────────────────────────────────────────┐          │
    │                                                         │          │
    ▼                                                         ▼          ▼
Balance System ◄──── Voucher Redemption              Rate Limiting    Admin Auth
    │                                                         │          │
    ▼                                                         ▼          ▼
Token Billing ◄──── Model Catalog (pricing)          Relay Endpoint   Admin Panel
    │                     │                               │              │
    ▼                     ▼                               ▼              ▼
Call Logging ◄──── Channel/Pool Management ────► Channel Selection   User Management
    │                     │                               │
    ▼                     ▼                               ▼
Usage Statistics    Routing Config ──────────────► ML Classification
    │                                                     │
    ▼                                                     ▼
Route Monitor ◄──────────────────────────────── Tiered Routing
```

Key dependency chains for the consolidation:

1. **Relay critical path:** API Key validate -> Balance check -> Route config -> Classify -> Channel select -> Upstream call -> Bill -> Log
2. **Admin critical path:** Admin auth -> Pool CRUD -> Model catalog -> Routing config -> Cache invalidation
3. **Monitoring path:** Call logs -> Usage stats (hourly aggregation via ARQ) -> Dashboard + Route monitor

## Feature Organization by Service (Post-Consolidation)

### api-service (all features except ML inference)

| Domain | Features | Controller Group |
|--------|----------|-----------------|
| User Auth | Register, login, logout, refresh, change password, email verify | `controllers/user/auth.py` |
| User Billing | Balance query, transactions, voucher redeem, usage analytics | `controllers/user/billing.py` |
| User Keys | API Key CRUD, per-key restrictions | `controllers/user/keys.py` |
| User Models | Public model catalog (read-only) | `controllers/user/models.py` |
| Admin Auth | Login, logout, refresh, change password | `controllers/admin/auth.py` |
| Admin Governance | Admin user CRUD, audit logs | `controllers/admin/admin_users.py`, `audit_logs.py` |
| Admin Users | User management (status, balance adjust, RPM) | `controllers/admin/user_management.py` |
| Admin Pools | Pool/channel/account CRUD, health check, model sync | `controllers/admin/pools.py` |
| Admin Models | Model vendor/category/catalog CRUD | `controllers/admin/model_catalog.py` |
| Admin Routing | Routing settings KV management | `controllers/admin/routing_settings.py` |
| Admin Vouchers | Generate/list/revoke voucher codes | `controllers/admin/vouchers.py` |
| Admin Dashboard | Summary stats, trends, RPM/TPM charts | `controllers/admin/dashboard.py` |
| Admin Monitoring | Route monitor, service logs | `controllers/admin/route_monitor.py`, `service_logs.py` |
| Relay | Chat completions, Anthropic messages, Responses API, model list | `controllers/relay/` |
| Internal | Routing config for inference-service | `controllers/internal/` |

### inference-service (ML classification only)

| Domain | Features |
|--------|----------|
| Classification | Score request complexity, return tier assignment |
| Config consumption | Pull routing config from api-service |

## MVP Recommendation (for the consolidation)

This refactoring is NOT adding features. The MVP is feature parity with the current 4-service system, delivered through 2 services.

**Priority 1 — Must work identically after consolidation:**
1. Relay endpoint (full request lifecycle: auth -> route -> forward -> bill -> log)
2. User auth + billing + key management
3. Admin auth + all management features
4. Dashboard and monitoring

**Priority 2 — Can be improved during consolidation:**
1. Call log schema (simplify to 14 columns per log-system-refactoring.md)
2. Runtime log format (pipe format per log-system-refactoring.md)
3. Routing config cache (DB+Redis replacing HTTP polling)
4. API Key validation (local DB replacing HTTP gateway)

**Defer to post-consolidation:**
- New protocol adapters (Google Gemini, etc.)
- New billing models (subscription tiers)
- New monitoring features (alerting, SLA tracking)

## Comparison with Reference Projects

### Feature Coverage Matrix

| Feature | new-api | one-api | LiteLLM | Portkey | EucalAI |
|---------|---------|---------|---------|---------|---------|
| OpenAI-compat endpoint | Yes | Yes | Yes | Yes | Yes |
| Multi-provider | 30+ | 20+ | 100+ | 50+ | 3 (focused) |
| Streaming | Yes | Yes | Yes | Yes | Yes |
| Token billing | Yes | Yes | Yes (enterprise) | Yes | Yes |
| Balance/quota | Yes | Yes | No (usage limits) | Yes | Yes |
| API Key mgmt | Yes | Yes | Yes | Yes | Yes |
| Channel pools | Yes | Yes | No (router config) | Yes (virtual keys) | Yes |
| Rate limiting | Basic | Basic | Yes | Yes | Yes (3-level) |
| ML-based routing | No | No | No | No | **Yes (unique)** |
| Intelligent cost routing | No | No | Router (rule-based) | Gateway (rule-based) | **Yes (ML-scored)** |
| Admin audit trail | Basic | No | No | Yes | **Yes (detailed)** |
| Multi-protocol native | No (OpenAI only) | No | Yes | Yes | **Yes** |
| User groups/tiers | Yes | Yes | No | Yes | No (by design) |
| Model aliases | Yes | Yes | Yes | Yes | No (by design) |
| Playground UI | Yes | No | Yes | Yes | No (by design) |
| Self-hosted models | No | No | Yes | No | No |
| Webhook/callbacks | No | No | Yes | Yes | No |
| Image/audio relay | Yes | Partial | Yes | Yes | No (future) |
| Caching (semantic) | No | No | Yes | Yes | No (future) |
| Guardrails/filters | No | No | No | Yes | No |
| A/B testing | No | No | No | Yes | No |
| Fallback chains | Yes | Yes | Yes | Yes | Yes |
| Load balancing | Weighted | Priority | RPM-based | Weighted | Weighted+priority+cooldown |

### Key Insight

EucalAI's differentiator is NOT breadth of provider support (LiteLLM wins that). It's the **ML-powered intelligent routing** that automatically optimizes cost by scoring query complexity. No other open-source relay does this. The consolidation should preserve and strengthen this advantage while simplifying the operational architecture.

## Sources

- Direct codebase analysis of EucalAI backend (4 services)
- `docs/architecture-refactoring.md` — target architecture
- `docs/log-system-refactoring.md` — new-api comparison (direct feature analysis)
- `services/admin-service/docs/database_schema.md` — admin feature inventory
- `services/user-service/docs/table_design_review.md` — user feature inventory
- Admin frontend types (`eucal-admin/src/types/index.ts`) — UI feature surface
- Training knowledge of new-api, one-api, LiteLLM, Portkey (MEDIUM confidence, not live-verified)
