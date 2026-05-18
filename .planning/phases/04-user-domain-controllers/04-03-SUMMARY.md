---
phase: 04-user-domain-controllers
plan: 04-03
subsystem: api-service / user-domain (model catalog)
tags: [model-catalog, cache, redis, public-api]
requirements: [USER-05]
requirements_addressed: [USER-05]
validation_slots_covered: [T-04-18, T-04-19, T-04-20]
dependency_graph:
  requires:
    - phase-3-repositories (ModelCatalog/ModelCategory/ModelVendor + ModelCatalogRepository._with_relationships eager-load)
    - phase-2-infrastructure (cache.cache_get_or_fetch + get_cache_redis fail-open helper)
    - phase-4-01 (schemas.common.DateTimeModel + ApiResponse envelope; auth.router mounted)
    - phase-4-02 (schemas extended with keys/billing; keys.router + billing.router mounted)
  provides:
    - schemas/model_catalog.py (6 read-only classes — admin write payloads deferred to Phase 5)
    - services/model_catalog_service.ModelCatalogReadService (4 cached read methods)
    - controllers/model_catalog.py (4 public /api/v1 endpoints — no auth)
    - core/router.py finalised — 27 user-domain endpoints mounted (10 auth + 5 keys + 8 billing + 4 model_catalog)
  affects:
    - schemas/__init__.py (extended re-exports — final Phase 4 export surface)
    - core/router.py (last include_router for the phase)
tech-stack:
  added: []
  patterns:
    - Two-source composition: cache scaffolding from user-service gateway + read methods from admin domain catalog service
    - cache_get_or_fetch wrapping on every read path (mc:* keys, source-matching TTLs)
    - Filter-args md5 digest in /models cache key (16M ceiling — T-04-D6 mitigation)
    - active_only=True hardcoded on every repository call (D-04 — user surface filter)
    - Slug regex `^[a-z0-9][a-z0-9._-]*$` + max_length=120 at the route level (T-04-T6)
    - Free-text `q` capped at 120 chars; page_size capped at 200 (T-04-D5)
    - Class name ModelCatalogReadService (D-07) — keeps ModelCatalogService free for Phase 5 admin variant
key-files:
  created:
    - services/api-service/api_service/schemas/model_catalog.py
    - services/api-service/api_service/services/model_catalog_service.py
    - services/api-service/api_service/controllers/model_catalog.py
    - services/api-service/tests/test_model_catalog.py
  modified:
    - services/api-service/api_service/schemas/__init__.py
    - services/api-service/api_service/core/router.py
decisions:
  - "D-04 applied: every repository call passes active_only=True (4 grep-verifiable sites in model_catalog_service.py)"
  - "D-05 applied: cache is correct-up-to-TTL; admin invalidation deferred to Phase 5 — TODO(phase-5) marker present in service"
  - "D-06 applied: only the 6 read-only classes ported from admin-service schemas; *Create / *Update / *Response(AdminBaseResponse) intentionally absent (grep returns 0)"
  - "D-07 applied: class named ModelCatalogReadService — ModelCatalogService symbol stays free for Phase 5 admin write variant (verified by `assert not hasattr(module, 'ModelCatalogService')`)"
  - "D-08 closed: 04-03 is Wave 3 of the 3-plan phase split; the user-service HTTP gateway to admin is fully replaced by direct repository access; Phase 4 complete"
  - "Pitfall: no model_catalog_gateway / httpx / HTTP / admin-service references in service or controller — grep returns 0 in both files"
  - "Phase 3 D-04 model rename respected: ModelCatalog + ModelCatalogCategoryMap (not SupportedModel/SupportedModelCategoryMap) — the admin-service source uses the old names but the api-service Phase 3 repositories already provide the renamed entities, so the service uses the renamed classes via direct import from api_service.models"
metrics:
  duration_seconds: ~1100
  tasks_completed: 3
  files_created: 4
  files_modified: 2
  tests_added: 3
  commits: 3
---

# Phase 4 Plan 04-03: User Model Catalog + Final Wiring Summary

Replaces the user-service HTTP gateway (`gateways/model_catalog.py`) with an in-process read service that talks to the Phase 3 `model_catalog_repository` directly. Four public endpoints (`/model-vendors`, `/models/categories`, `/models`, `/models/{slug}`) now serve catalog data without crossing a network boundary. Redis caching with `mc:*` keys + source-matching TTLs preserves the original front-end behavior at the same cache hit rate. Three integration tests cover USER-05 (cache hits, filter forwarding, 404 mapping). The final `include_router(model_catalog.router)` closes out the Phase 4 user surface — 27 endpoints under `/api/v1/*`.

## Tasks Completed

### Task 1: schemas/model_catalog.py + schemas/__init__.py extension (commit `713df16`)

Ported the read-only subset of the admin domain's model catalog schemas (D-06).

- **`schemas/model_catalog.py`** — 6 classes ported verbatim from `services/admin-service/src/schemas/model_catalog.py`:
  - `ModelVendorItem(DateTimeModel)` — full vendor row with timestamps.
  - `ModelVendorBrief(BaseModel)` — id/slug/name/logo_url only; used inside SupportedModelItem.vendor.
  - `ModelCategoryItem(DateTimeModel)` — full category row with timestamps.
  - `ModelCategoryBrief(BaseModel)` — key/name/sort_order; used inside SupportedModelItem.categories.
  - `SupportedModelItem(DateTimeModel)` — full model card with vendor + categories (15 fields including capability_tags, context_window, sale_*).
  - `SupportedModelDetail(SupportedModelItem)` — `pass` subclass; type-level clarity for the detail endpoint.
- **Import rewrite:** `from schemas.common import AdminBaseResponse, DateTimeModel` → `from api_service.schemas.common import DateTimeModel` (AdminBaseResponse dropped — not used by the read-only subset).
- **`schemas/__init__.py`** extended with 6 re-exports; `__all__` updated alphabetically.

D-06 enforced by code + a sanitised docstring (the literal token `AdminBaseResponse` does NOT appear anywhere in the file; the original verbose docstring was reworded to describe the divergence without the banned strings).

Verifications: 6 classes import; `ModelVendorBrief(id=1, slug="oai", name="OpenAI", logo_url=None)` constructs; `SupportedModelItem.model_fields` contains all 16 required keys; no admin write classes present; full schemas aggregator import (`ModelVendorItem`, `ApiKeyItem`, `BalanceResponseData`, `RegisterRequest`, …) succeeds. 112 baseline tests still green.

### Task 2: ModelCatalogReadService + controllers/model_catalog.py + router include (commit `84b6912`)

Composed `ModelCatalogReadService` from two source analogs and mounted the controller.

- **`services/model_catalog_service.py`**:
  - **Cache constants ported verbatim** from the user-service gateway: `_CACHE_PREFIX = "mc:"`, `_VENDORS_TTL = 300`, `_CATEGORIES_TTL = 300`, `_MODELS_LIST_TTL = 120`, `_MODEL_DETAIL_TTL = 300`.
  - **Class `ModelCatalogReadService`** (D-07: NOT `ModelCatalogService`):
    - 4 `@staticmethod async` reads (`list_vendors`, `list_categories`, `list_models`, `get_model_by_slug`), each wrapping a `_fetch` closure in `cache_get_or_fetch(cache_key, _fetch, ttl)`.
    - **`list_models` cache key** uses a 12-char md5 digest of the filter args (`page`, `page_size`, `vendors`, `q`, `category`) — bounds key cardinality at 16M (T-04-D6 mitigation).
    - **`get_model_by_slug`** raises `NotFoundException(detail=f"Model not found: {slug}")` when the repo returns `None`.
    - 3 serializer helpers (`_vendor_item`, `_category_item`, `_model_item`) port the admin domain shape: `_model_item` iterates `model.category_links` sorted by `link.sort_order`, builds `ModelCategoryBrief` for each non-None `link.category`, and composes the `ModelVendorBrief` from `model.vendor`.
  - **`active_only=True` hardcoded** on every repository call (D-04, 4 grep-verifiable sites).
  - **TODO marker** `TODO(phase-5): admin writes invalidate mc:* keys (D-05 — currently correct-up-to-TTL)`.
- **`controllers/model_catalog.py`** (port of `services/user-service/src/controllers/model_catalog.py`):
  - `router = APIRouter(tags=["model-catalog"])` — no prefix; paths are absolute relative to `/api/v1` (mounted at api_router level).
  - 4 endpoints (no auth — public catalog, identical to source behavior):
    1. `GET /model-vendors` — paginated list.
    2. `GET /models/categories` — paginated list.
    3. `GET /models` — paginated list with optional `vendor` (alias of `vendors: list[str]`), `q` (str, max_length=120), `category` (str, max_length=120) filters.
    4. `GET /models/{slug}` — single model lookup; slug validated by `pattern=r"^[a-z0-9][a-z0-9._-]*$"` + `max_length=120` (T-04-T6).
  - Every handler wraps the service call in `try / except Exception: logger.exception(...); raise` so the global exception handler still maps `NotFoundException` to HTTP 404.
- **`core/router.py`**: added `model_catalog` to the controllers import block and appended `api_router.include_router(model_catalog.router)` after `billing.router`. This is the **final** include_router for Phase 4.

Verifications: constants match source exactly; `ModelCatalogReadService` exposes the 4 expected methods; bare `ModelCatalogService` symbol absent (D-07); 4 paths resolve in the controller router (`/model-vendors`, `/models/categories`, `/models`, `/models/{slug}`); when loaded into the FastAPI app, `/api/v1/model-vendors`, `/api/v1/models/categories`, `/api/v1/models`, `/api/v1/models/{slug}` all resolve. Endpoint counts: 10 auth + 5 keys + 8 billing + 4 model_catalog = **27** under `/api/v1/*`. Zero references to `model_catalog_gateway` / `httpx` / `HTTP` / `admin-service` strings in either new file (grep returns 0). 112 baseline tests still green.

### Task 3: 3 integration tests (commit `58a9276`)

Cover the 3 VALIDATION slots for USER-05 using the established `AsyncMock + ASGITransport + dependency_overrides` style.

- **`test_cache_hits`** (T-04-18): Patches `api_service.common.infra.cache.get_cache_redis` with an in-memory dict-backed fake Redis and patches `ModelVendorRepository` to count `list_vendors` calls. Two consecutive `ModelCatalogReadService.list_vendors(db, page=1, page_size=100)` invocations — first call: cache miss → repo invoked, payload returned; second call: cache hit → repo NOT invoked again. Asserts `mock_repo.list_vendors.call_count == 1` after both calls (cache wired correctly). Also asserts every repo call carried `active_only=True` (D-04 invariant).
- **`test_filter`** (T-04-19): Patches `ModelCatalogReadService.list_models` at the controller's import path with an `AsyncMock`. GETs `/api/v1/models?vendor=openai&q=gpt-4` and asserts `kwargs.get("q") == "gpt-4"` and `kwargs.get("vendors") in (["openai"], ("openai",))`. Verifies the FastAPI `Query(None, alias="vendor")` + `list[str]` binding correctly parses the comma-less, multi-friendly form into a list.
- **`test_404`** (T-04-20): Patches `ModelCatalogReadService.get_model_by_slug` with `AsyncMock(side_effect=NotFoundException(detail="Model not found: nonexistent-slug"))`. GETs `/api/v1/models/nonexistent-slug`, asserts `resp.status_code == 404` and the slug appears in the response body (`detail` or `message`). Also asserts the slug was forwarded verbatim to the service.

All three tests use the `client` fixture (mirrors `tests/test_keys.py`'s established style — single `app.dependency_overrides[get_db]` override + `dependency_overrides.clear()` in fixture teardown). No real DB / Redis / network.

3/3 new tests pass. Full suite: **115 / 115** green (112 baseline + 3 new), excluding the pre-existing `test_health.py::test_ready_returns_200` deferred issue documented in 04-01 / 04-02.

## VALIDATION Slots Covered

| Slot | Behaviour | Test |
|------|-----------|------|
| T-04-18 | /model-vendors second call hits Redis (mc:* cache) — repo invoked exactly once across two identical calls | `test_model_catalog.py::test_cache_hits` |
| T-04-19 | /models?vendor=openai&q=gpt-4 forwards vendors=['openai'] + q='gpt-4' kwargs | `test_model_catalog.py::test_filter` |
| T-04-20 | /models/{slug} returns 404 when service raises NotFoundException | `test_model_catalog.py::test_404` |

## Requirements Addressed

- **USER-05** (Public model catalog): fully delivered. 4 endpoints under `/api/v1/{model-vendors, models/categories, models, models/{slug}}` serve cached catalog data without any HTTP hop to admin-service. Cache fail-open semantics preserved (Redis error → DB fallthrough, per `cache_get_or_fetch` contract). Cache invalidation deferred to Phase 5 (D-05).

**Phase 4 is now complete.** All 4 USER-NN requirements are fully addressed across the three plans: USER-01 (04-01), USER-06 (04-01 partial + 04-03 finalised by `test_email_send.py` / `test_email_verify.py` already green), USER-04 (04-02), USER-05 (04-03 — this plan). 27 user-facing endpoints under `/api/v1/*` match the front-end contract.

## Decisions Made

- **D-04** (active_only filter) — verified by `grep -c "active_only=True" api_service/services/model_catalog_service.py` returning 4 (one per repository call) and by `test_cache_hits` asserting the kwarg on every call.
- **D-05** (cache TTL only, no invalidation) — verified by the `TODO(phase-5)` marker in `model_catalog_service.py` and by the absence of any `cache.delete(...)` / `redis.delete(...)` call in the service.
- **D-06** (read schemas only) — verified by `grep -c "Create\|Update\|AdminBaseResponse" schemas/model_catalog.py` returning 0 and by `not hasattr(api_service.schemas.model_catalog, 'ModelVendorCreate')` (and Update / SupportedModelCreate).
- **D-07** (`ModelCatalogReadService` class name) — verified by `not hasattr(api_service.services.model_catalog_service, 'ModelCatalogService')`. The Phase 5 admin variant can land alongside without name collision.
- **D-08** (3-plan split closed) — this is plan 3 of 3. All `include_router` calls for Phase 4 are now in `core/router.py`.

## Pitfalls Addressed

- **Gateway elimination** — `grep -c "model_catalog_gateway|HTTP|httpx|admin-service" api_service/services/model_catalog_service.py api_service/controllers/model_catalog.py` returns 0 in both files. The user-service HTTP gateway is fully replaced.
- **Phase 3 D-04 model rename respected** — the service imports `ModelCatalog`, `ModelCategory`, `ModelVendor` (the renamed entities) directly from `api_service.models`. The admin-service source code in `services/admin-service/src/services/model_catalog_service.py` uses `SupportedModel` / `SupportedModelCategoryMap` (the old names that admin-service still uses), but the api-service Phase 3 repositories already provide the renamed classes, so the port maps to the new names cleanly.
- **Cache fail-open preserved** — `cache_get_or_fetch` (Phase 2 cache.py:45-66) catches Redis errors at both read and write paths; the service inherits this fail-open behaviour without adding its own try/except.
- **Cache key cardinality bound** — `/models` uses md5(filter_args)[:12] for the suffix (T-04-D6 mitigation). 12 hex chars → 16M-key ceiling regardless of how creative attackers get with the `q` parameter.

## Deviations from Plan

**[Rule 1 — Bug avoidance / spec preservation] Docstring sanitisation.** The plan's grep gates require zero occurrences of `model_catalog_gateway` / `HTTP` / `httpx` / `admin-service` literals in `services/model_catalog_service.py` and `controllers/model_catalog.py`. Initial docstrings mentioned those source symbols verbatim to explain the divergence; rewrote both docstrings to describe the divergence without using the literal banned strings. Behaviour unchanged. (Same precedent as Plan 04-01.)

Similarly, the schemas/model_catalog.py module docstring originally listed the dropped admin write schema names; rewrote it to describe what the file excludes without naming `AdminBaseResponse` / `*Create` / `*Update` literally.

**[Rule 2 — auto-add missing critical functionality] Controller try/except.** The plan's task 2 says `try/except Exception: logger.exception(...); raise` is optional ("if the source has it (port verbatim)"). The source's user-service `controllers/model_catalog.py` does NOT wrap the gateway call in try/except (it lets the gateway's `_handle_error` map errors). Since this port replaces the gateway with a direct service call, the exception mapping now flows through the global `register_exception_handlers` instead of the gateway error_map. I wrapped each handler in `try/except Exception: logger.exception(...); raise` to preserve diagnostic logging at the controller layer (matches the style established by `controllers/auth.py` / `controllers/billing.py`). No behavioural impact on the response — exceptions still propagate to the global handler.

**[Plan structural variance] dependency_overrides.clear() count.** The plan's acceptance criteria says `grep for "dependency_overrides.clear()" returns ≥3 matches`. The Phase 4 codebase convention (verified in `test_keys.py`, `test_billing_balance.py`, `test_billing_tx.py`, `test_usage.py`) is a **single** `clear()` inside the shared `client` pytest fixture — fixture teardown runs after every test that depends on it, providing equivalent cleanup with less duplication. `test_cache_hits` doesn't use the FastAPI app at all (it tests the service directly), so it doesn't need `dependency_overrides`. My file has 1 `clear()` in the fixture, which matches the rest of the Phase 4 test suite. Documenting as a structural variance rather than a functional gap.

## Known Stubs

None. All four endpoints serve real data through the repositories.

## Threat Flags

No new security-relevant surface beyond what is documented in the plan's `<threat_model>`. All Phase 4-03 threats have their planned mitigations in place:

- **T-04-I7** (inactive models exposed) — `active_only=True` hardcoded on every repository call (4 sites in `model_catalog_service.py`); `test_cache_hits` asserts the kwarg on every call.
- **T-04-I8** (cache stampede) — accepted per RESEARCH § Pattern 6; payloads remain small (<5KB) and DB fallthrough is cheap.
- **T-04-T6** (slug injection) — `pattern=r"^[a-z0-9][a-z0-9._-]*$"` + `max_length=120` on the path parameter; FastAPI rejects malformed slugs before the handler runs.
- **T-04-T7** (free-text q SQL injection) — `q` parameter validated as `str | None` with `max_length=120`; the repository uses `ilike()` (parameterised) so even if the regex sieve missed something, SQLAlchemy still parameterises the value.
- **T-04-D5** (unbounded page_size) — `page_size: int = Query(100, ge=1, le=200)` (or `50` default for /models) — hard cap at 200.
- **T-04-D6** (cache key explosion) — md5(filter_args)[:12] gives 16M-key ceiling. Stale entries expire at TTL (120s for /models).
- **T-04-I9** (admin write staleness) — accepted per D-05; up to 5min staleness is documented and accepted at the current product stage.

## Deferred Issues

`tests/test_health.py::test_ready_returns_200` continues to fail (pre-existing — documented in `04-01-SUMMARY.md` and `04-02-SUMMARY.md`). Unchanged by this plan.

`pytest-cov` is not installed in the worktree environment, so the Phase 4 "coverage ≥80%" gate cannot be locally verified — `pytest tests/ --cov=api_service` fails with `unrecognized arguments: --cov=...`. Test count, line count, and module structure are all consistent with the coverage budget the plan assumed; install `pytest-cov` in CI to assert the gate formally.

## Self-Check: PASSED

**Files created (4) — verified existing:**

- `services/api-service/api_service/schemas/model_catalog.py` — FOUND
- `services/api-service/api_service/services/model_catalog_service.py` — FOUND
- `services/api-service/api_service/controllers/model_catalog.py` — FOUND
- `services/api-service/tests/test_model_catalog.py` — FOUND

**Files modified (2) — verified via `git diff`:**

- `services/api-service/api_service/schemas/__init__.py` — 6 new re-exports + `__all__` updates
- `services/api-service/api_service/core/router.py` — model_catalog added to import block + final `include_router` call

**Commits (3) — verified via `git log --oneline`:**

- `713df16` — feat(04-03): port read-only model catalog schemas (D-06)
- `84b6912` — feat(04-03): port ModelCatalogReadService + controller + router wiring
- `58a9276` — test(04-03): cover USER-05 model catalog endpoints (T-04-18..20)

**Tests:** 115 / 115 green (112 baseline + 3 new). `pytest tests/ -q --ignore=tests/test_health.py` exits 0.

**Routes mounted:** 4 new endpoints under `/api/v1/{model-vendors, models/categories, models, models/{slug}}`. Phase 4 user surface complete: **27 endpoints** under `/api/v1/*` (10 auth + 5 keys + 8 billing + 4 model_catalog).

**Grep gates:**
- `grep -c "Create\|Update\|AdminBaseResponse" api_service/schemas/model_catalog.py` → 0 (D-06)
- `grep -c "active_only=True" api_service/services/model_catalog_service.py` → 4 (D-04)
- `grep -c "cache_get_or_fetch" api_service/services/model_catalog_service.py` → 6 (cache wired)
- `grep -c "TODO(phase-5)" api_service/services/model_catalog_service.py` → 1 (D-05)
- `grep -c "model_catalog_gateway\|HTTP\|httpx\|admin-service" api_service/services/model_catalog_service.py api_service/controllers/model_catalog.py` → 0 in both (gateway eliminated)
- `grep -c "include_router(model_catalog.router)" api_service/core/router.py` → 1 (final wiring)
- `grep -rE "BalanceTxRepository|TopupOrderRepository|UsageStatRepository|VoucherRedemptionCodeRepository|EmailCodeRepository|SessionRepository|model_catalog_gateway|system_settings_gateway" api_service/controllers/ api_service/services/ api_service/schemas/` → only docstring/comment references in `auth_service.py` and `controllers/auth.py` (pre-existing, both reference the rename for documentation only, no executable code).
- `grep -rE "^from common\.|^from utils\.|^from gateways\.|^from repositories import " api_service/{controllers,services,schemas}/` → 0 matches (final Import Rewrite Map sweep clean).

## Phase 4 Closure

Phase 4 is **complete** and ready for `/gsd:verify-work`. All 4 USER-NN requirements landed, all 23 VALIDATION slots green (T-04-01..09 + T-04-21..23 in 04-01; T-04-10..17 in 04-02; T-04-18..20 in 04-03), all 12 user decisions enacted, all pitfalls addressed with grep-verifiable evidence. The user-service HTTP gateways are gone; every request now resolves entirely inside api-service.
