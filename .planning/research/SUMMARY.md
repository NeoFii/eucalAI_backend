# Project Research Summary

**Project:** EucalAI Backend — Architecture Consolidation (4 microservices to 2)
**Domain:** LLM API Gateway / Relay Platform (service consolidation refactoring)
**Researched:** 2026-05-18
**Confidence:** HIGH

## Executive Summary

This is a consolidation refactoring of a production LLM API relay platform. The project merges 4 microservices (admin-service, user-service, router-service, inference-service) into 2 (api-service + inference-service), eliminating unnecessary cross-service HTTP calls that add ~20-50ms latency per relay request. The entire technology stack is already validated in production — no greenfield decisions are needed.

The core challenge is merging three Python/FastAPI services into a single layered monolith without breaking the relay hot path, billing integrity, or admin functionality.

## Key Findings

### Stack
- Entire stack already deployed and validated — no technology changes needed
- Critical: `pool_size=5, max_overflow=10` per worker (60 max + ARQ = ~70 vs MySQL 151 limit)
- Drop litellm dependency — direct openai + anthropic SDKs give full control
- Pin `bcrypt>=3.2.0,<4.0.0` for passlib compatibility

### Features
- Feature parity is the goal — zero feature additions
- ML-powered intelligent routing (Qwen2.5-7B + CG-TabM) is the key differentiator to protect
- Consolidation eliminates 3 HTTP calls per relay request (api-key validate, call-log batch, config refresh)

### Architecture
- Layered monolith: Controllers -> Services -> Repositories -> ORM -> Single DB
- 4 auth modes coexist via distinct `Depends()` functions (no global middleware)
- Relay hot path: only 1 remote call remains (inference-service classify)
- Build order strictly dependency-driven: scaffold -> admin+user -> relay -> inference -> deploy

### Pitfalls (Top 5)
1. **Session scope leakage** — fire-and-forget tasks MUST use own session via `get_db_context()`
2. **DB pool exhaustion** — 4 workers x 15 connections = 60, keep under MySQL 151 limit
3. **Snowflake ID collision** — each uvicorn worker needs unique worker_id (`os.getpid() % 32`)
4. **DB migration data loss** — use maintenance window, verify row counts, keep old DBs 7 days
5. **Billing race condition** — monitor FOR UPDATE lock wait time post-merge

## Cross-Cutting Concerns

1. **Concurrency control** — merge converts network boundaries into in-process concurrency
2. **Cache consistency** — 60s TTL on relay path, admin writes trigger invalidation
3. **Resource budgeting** — 4 workers + MySQL + Redis + ARQ on 2h4g server
4. **ID generation safety** — multi-process needs per-worker Snowflake coordination
5. **Zero-downtime migration** — maintain service continuity during architecture swap

## Phase Recommendations

| Phase | Focus | Effort | Risk |
|-------|-------|--------|------|
| 1 | Scaffold + Common + DB Merge | 2-3d | Low |
| 2 | Admin + User Domain Migration | 3-4d | Medium |
| 3 | Relay Integration | 3-4d | High |
| 4 | Inference-Service Update | 0.5d | Low |
| 5 | Deployment + Validation | 2-3d | Medium |

**Critical path:** Phase 1 -> 2 -> 3 -> 5 = 10-14 days
**Parallel:** Phase 4 runs alongside Phase 3

## Research Flags

- **Phase 3 needs deeper research:** call_lifecycle has 6 phases with circuit breakers + streaming
- **Phase 5 needs environment validation:** DB merge procedure, memory tuning
- **Phases 1, 2, 4:** Standard patterns, skip additional research

## Confidence Assessment

| Area | Level | Notes |
|------|-------|-------|
| Stack | HIGH | All in production, versions verified |
| Features | HIGH | Feature parity, no new features |
| Architecture | HIGH | Patterns well-understood, docs detailed |
| Pitfalls | HIGH | Based on direct codebase analysis |

---
*Research completed: 2026-05-18*
*Ready for roadmap: yes*
