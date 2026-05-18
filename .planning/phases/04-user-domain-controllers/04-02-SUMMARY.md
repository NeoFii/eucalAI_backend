---
phase: 04-user-domain-controllers
plan: 04-02
subsystem: api-service / user-domain (keys + billing)
tags: [api-keys, billing, balance, voucher, topup, usage, analytics]
requirements: [USER-04]
requirements_addressed: [USER-04]
validation_slots_covered: [T-04-10, T-04-11, T-04-12, T-04-13, T-04-14, T-04-15, T-04-16, T-04-17]
dependency_graph:
  requires:
    - phase-3-repositories (BillingRepository merged, VoucherRepository renamed, ApiKeyRepository preserved, UserRepository.get_by_id(for_update=...))
    - phase-4-01 (require_active_user, ApiResponse, AuthBaseResponse, DateTimeModel, common.utils.api_key_policy, common.utils.timezone, settings.MAX_API_KEYS_PER_USER)
  provides:
    - schemas/keys.py (ApiKeyItem key_prefix only, ApiKeyCreateData plaintext-once, ApiKeyCreateRequest/UpdateRequest)
    - schemas/billing.py (BalanceResponseData with computed available_balance, BalanceTransactionItem, TopupOrderItem, VoucherRedeem*, UsageAnalytics*, UsageAnalyticsRange Literal, ApiCallLogItem.from_orm_instance)
    - services/api_key_service.ApiKeyService (full CRUD + validate_by_hash for Phase 6 relay)
    - services/balance_service.BalanceService (all 7 wallet-mutation methods preserve SELECT FOR UPDATE + ref_id idempotency)
    - services/topup_order_service.TopupOrderService (BillingRepository.topup_* routing)
    - services/voucher_service.VoucherService (VoucherRepository class rename, ref_id idempotency in redeem_code)
    - services/usage_stat_service.UsageStatService (9 BillingRepository.stat_* sites, 48h granularity switch)
    - controllers/keys.py (5 endpoints under /api/v1/keys)
    - controllers/billing.py (8 endpoints under /api/v1/billing/*)
  affects:
    - core/router.py (keys.router + billing.router mounted after auth.router)
    - schemas/__init__.py (extended re-exports for keys + billing)
tech-stack:
  added: []
  patterns:
    - SELECT ... FOR UPDATE on user row before every BalanceService wallet mutation (11 for_update=True call sites in balance_service.py)
    - ref_id idempotency on BalanceTransaction inserts via BillingRepository.exists_by_ref(tx_type, ref_type, ref_id)
    - Soft delete on user_api_keys (deleted_at set, no DELETE SQL)
    - Plaintext API key returned ONLY once in ApiKeyCreateData on POST /keys; ApiKeyItem exposes key_prefix only
    - ApiCallLogItem.from_orm_instance loads api_key.name via eager-loaded relationship for /billing/usage/logs
    - try/except Exception + logger.exception on every controller endpoint
key-files:
  created:
    - services/api-service/api_service/schemas/keys.py
    - services/api-service/api_service/schemas/billing.py
    - services/api-service/api_service/services/api_key_service.py
    - services/api-service/api_service/services/balance_service.py
    - services/api-service/api_service/services/topup_order_service.py
    - services/api-service/api_service/services/voucher_service.py
    - services/api-service/api_service/services/usage_stat_service.py
    - services/api-service/api_service/controllers/keys.py
    - services/api-service/api_service/controllers/billing.py
    - services/api-service/tests/test_keys.py
    - services/api-service/tests/test_api_key_service.py
    - services/api-service/tests/test_billing_balance.py
    - services/api-service/tests/test_billing_tx.py
    - services/api-service/tests/test_voucher.py
    - services/api-service/tests/test_topup.py
    - services/api-service/tests/test_usage.py
    - services/api-service/tests/test_usage_stat_service.py
  modified:
    - services/api-service/api_service/schemas/__init__.py
    - services/api-service/api_service/core/router.py
decisions:
  - "D-01 honored: no internal_* controllers ported. Public /keys + /billing surface only."
  - "D-03 honored: 1:1 port of user-service schemas/keys.py (83 lines) + schemas/billing.py (190 lines), no consolidation, no admin schemas."
  - "D-08 honored: 04-02 is Wave 2 of the 3-plan phase split; depends on 04-01 auth foundations."
  - "Phase 3 D-04 repo merge translated at every call site: BalanceTxRepository / TopupOrderRepository / UsageStatRepository → BillingRepository.*; VoucherRedemptionCodeRepository → VoucherRepository."
  - "Pitfall 1 enforced: no deleted class names anywhere in services (grep returns 0 across api_key/balance/topup_order/voucher/usage_stat)."
  - "Pitfall 3 enforced: get_db_session → get_db at all controller call sites (grep returns 0 in keys.py + billing.py)."
  - "Pitfall 8 enforced: usage_stat_service does NOT re-filter error_code='invalid_model' — BillingRepository.stat_list_analytics_logs / stat_list_logs_for_hour already embed _exclude_invalid_model()."
  - "Pitfall 10 enforced: VoucherService.normalize_code = raw.strip().lower() is the single source of truth; controller does NOT normalize."
  - "Security invariant: ApiKeyItem.model_fields contains key_prefix but NEITHER key NOR key_hash; ApiKeyCreateData is the only shape with plaintext key."
  - "Security invariant: ApiKeyService.delete is soft-only (deleted_at = now(); await db.commit()); db.delete never called."
  - "Security invariant: every BalanceService wallet method calls _get_user(db, user_id, for_update=True) BEFORE mutation — 11 for_update=True call sites verified."
  - "Security invariant: VoucherService.redeem_code adds an exists_by_ref short-circuit BEFORE balance mutation, in addition to source's code.status check, to satisfy must_haves spec on ref_id idempotency."
metrics:
  duration_seconds: ~1145
  tasks_completed: 3
  files_created: 17
  files_modified: 2
  tests_added: 18
  commits: 3
---

# Phase 4 Plan 04-02: User Keys + Billing Controllers Summary

Ports the 5 `/keys` + 8 `/billing` endpoints and their 5 supporting services from `user-service` into `api-service`. Every wallet mutation preserves `SELECT ... FOR UPDATE` row locking on `users` and `ref_id` idempotency against `balance_transactions`. Plaintext API key returned exactly once on create; subsequent reads expose only `key_prefix`. 13 user-domain endpoints now live at `/api/v1/keys/*` and `/api/v1/billing/*` next to the existing `/api/v1/auth/*` from 04-01.

## Tasks Completed

### Task 1: schemas + 4 supporting services (commit `f161a3b`)

Landed the schemas + four of the five services (BalanceService deferred to Task 2 due to size).

- **`schemas/keys.py`** (83 lines, 1:1 from `user-service/src/schemas/keys.py`): `ApiKeyItem` exposes `key_prefix` only (NEVER `key` or `key_hash`); `ApiKeyCreateData` is the ONLY shape with the plaintext `key` field; `ApiKeyCreateRequest`/`ApiKeyUpdateRequest` chain `normalize_allowed_models` + `normalize_allow_ips` + `to_shanghai_naive` validators.
- **`schemas/billing.py`** (190 lines): `BalanceResponseData.available_balance` `@computed_field` (= `balance - frozen_amount`); `UsageAnalyticsRange` `Literal["8h", "24h", "7d", "30d"]`; `ApiCallLogItem.from_orm_instance` classmethod surfaces `api_key.name` via the eager-loaded relationship.
- **`schemas/__init__.py`**: extended to re-export the 19 new classes (`Api*`, `Balance*`, `Topup*`, `Usage*`, `Voucher*`).
- **`services/api_key_service.py`** (196 lines): `ApiKeyRepository` preserved as-is, only import paths rewritten. `create` returns `(api_key_obj, raw_plaintext)`; `delete` sets `deleted_at = now()` (soft); `_refresh_status` chain (DISABLED → EXPIRED → EXHAUSTED → ACTIVE) preserved verbatim; `validate_by_hash` ported for Phase 6 relay (no callers in this plan).
- **`services/topup_order_service.py`** (82 lines): every `TopupOrderRepository(db).*` call rewritten to `BillingRepository(db).topup_*`. `_generate_order_no = "TP" + YYYYMMDD + 8 chars` preserved verbatim. Lazy import of `BalanceService` to avoid module-load cycle.
- **`services/voucher_service.py`** (185 lines): class rename `VoucherRedemptionCodeRepository` → `VoucherRepository` applied; balance-side calls rewritten to `BillingRepository.add_tx` / `.exists_by_ref`. `normalize_code = raw.strip().lower()` (Pitfall 10, single source of truth). `redeem_code` acquires user with `for_update=True` BEFORE mutation; adds `exists_by_ref` short-circuit BEFORE balance mutation per `must_haves` spec.
- **`services/usage_stat_service.py`** (338 lines): all 9 `UsageStatRepository(db).*` call sites rewritten to `BillingRepository(db).stat_*`; per-row bucket inserts use `repo.session.add(bucket)` since there's no per-row helper. `_build_usage_analytics_window` dispatch for 8h/24h/7d/30d; explicit start/end → `granularity = 'hour' if (end - start) <= timedelta(hours=48) else 'day'`. Pitfall 8 honored: NO service-layer re-filter of `error_code='invalid_model'`.

Verifications: schemas + services importable, `ApiKeyItem.model_fields` has `key_prefix` but no `key`/`key_hash`, `BalanceResponseData(balance=1000, frozen_amount=100).model_dump()["available_balance"] == 900`, `VoucherService.normalize_code("  ABC123 ") == "abc123"`, grep for deleted repo class names returns 0 across all four new service files. Baseline 94 tests stay green.

### Task 2: BalanceService + controllers + router mount (commit `dd6f8ee`)

The biggest service (411 LOC) plus both controllers and router wiring.

- **`services/balance_service.py`**: 7 wallet-mutation methods (`consume_for_call_log`, `freeze`, `settle`, `refund`, `topup`, `admin_adjust`, plus `redeem_code` thin wrapper to `VoucherService`) + read helpers (`get_balance`, `list_transactions`, `list_all_transactions`). Every mutation calls `_get_user(db, user_id, for_update=True)` BEFORE any state change. 11 `for_update=True` call sites verified. All `BalanceTxRepository(db).*` rewritten to `BillingRepository(db).{add_tx, exists_by_ref, list_tx_for_user, list_tx_all}`; `TopupOrderRepository.get_for_user_by_order_no` → `BillingRepository.topup_get_for_user_by_order_no`. The `_transaction_exists` helper short-circuits duplicate inserts on `(tx_type, ref_type, ref_id)` triples.
- **`controllers/keys.py`** (107 LOC): `APIRouter(prefix="/keys", tags=["keys"])`, 5 endpoints (GET list, POST create returns `{"key": raw_key, "item": ApiKeyItem}`, PATCH update with `provided_fields=set(payload.model_fields_set)`, POST disable, DELETE soft-delete). All depend on `get_db` (Pitfall 3) + `require_active_user`.
- **`controllers/billing.py`** (309 LOC): `APIRouter(prefix="/billing", tags=["billing"])`, 8 endpoints. `_build_list_params` helper enforces `MAX_BILLING_RANGE_DAYS = 90` via `ListParams.validate_time_range`. Key-ownership pre-check `await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))` on every endpoint that accepts `api_key_id`. `ApiCallLogItem.from_orm_instance(item)` on usage logs to surface `api_key.name`. Every handler wraps the service call in `try/except Exception: logger.exception(...); raise` per PATTERNS.
- **`core/router.py`**: added `from api_service.controllers import auth, billing, keys` (alphabetical) + two new `include_router` lines after the existing `auth.router` mount.

Verifications: `from api_service.main import app` produces an app where `/api/v1/keys`, `/api/v1/billing/balance`, `/api/v1/billing/transactions` all resolve; api_router has 23 routes total (10 auth + 5 keys + 8 billing); `grep -c "BalanceTxRepository|TopupOrderRepository|UsageStatRepository|VoucherRedemptionCodeRepository" balance_service.py` returns 0; `grep -c "for_update=True" balance_service.py` returns 11. Baseline 94 tests stay green.

### Task 3: 8 test files covering T-04-10..17 (commit `6de860c`)

Used the same `ASGITransport(app=app)` + `dependency_overrides[get_db] / [require_active_user]` style as the 04-01 auth tests. All tests rely on `AsyncMock` / `MagicMock` — no real DB or Redis.

- **`tests/test_keys.py`** — T-04-10 + T-04-11: POST returns plaintext exactly once in `data.key`; `data.item` has `key_prefix` but neither `key` nor `key_hash`. GET list of two keys: every item lacks `key`/`key_hash`.
- **`tests/test_api_key_service.py`** — T-04-12 + 3 branch tests: `delete` sets `api_key.deleted_at = now()` and `db.commit` is awaited; `db.delete` never called. `_refresh_status` branches verified: DISABLED short-circuits; EXPIRED set when `expires_at` is in the past; ACTIVE promoted when unexpired + not exhausted.
- **`tests/test_billing_balance.py`** — T-04-13: GET `/billing/balance` returns int fields + `available_balance == 1000 - 100 == 900`.
- **`tests/test_billing_tx.py`** — T-04-14: GET `/billing/transactions?type=1` forwards `tx_type=1` kwarg to `BalanceService.list_transactions`; paginated body shape verified.
- **`tests/test_voucher.py`** — T-04-15: two consecutive `VoucherService.redeem_code` calls with `exists_by_ref` side_effect `[False, True]` — `add_tx.call_count == 1` after both calls. The single insert carries `ref_type="voucher_code"`, `ref_id=str(code.id)`, `type=BalanceTransaction.TYPE_VOUCHER_REDEEM`. Every `UserRepository.get_by_id` call is verified to pass `for_update=True` (SELECT FOR UPDATE invariant). Plus `normalize_code` strip+lower verification.
- **`tests/test_topup.py`** — GET `/topup-orders` returns a paginated list of user-scoped orders; `_generate_order_no()` produces an 18-char string starting with `TP`.
- **`tests/test_usage.py`** — T-04-16: GET `/billing/usage?start=2024-01-01&end=2024-06-01` (152 days) → HTTP 422 with the 90-day cap message surfaced.
- **`tests/test_usage_stat_service.py`** — T-04-17: `_build_usage_analytics_window` for 8h/24h returns `"hour"`, for 7d/30d returns `"day"`. `get_usage_analytics(start=t0, end=t0+48h)` produces `granularity="hour"`; `t0+49h` flips to `"day"` — the 48-hour boundary is enforced.

All 18 new tests pass. Full suite: 112 passing (94 baseline + 18 new), excluding the pre-existing `test_health.py::test_ready_returns_200` deferred issue.

## VALIDATION Slots Covered

| Slot | Behaviour | Test |
|------|-----------|------|
| T-04-10 | POST /keys returns plaintext exactly once + ApiKeyItem hides key/key_hash | `test_keys.py::test_create_returns_plaintext_once` |
| T-04-11 | GET /keys never exposes plaintext or hash | `test_keys.py::test_list_no_secrets` |
| T-04-12 | DELETE /keys/{id} is a soft delete (deleted_at set) | `test_api_key_service.py::test_delete_is_soft` |
| T-04-13 | /billing/balance returns int fields + computed available_balance | `test_billing_balance.py::test_balance_fields` |
| T-04-14 | /billing/transactions paginates + filters by type | `test_billing_tx.py::test_tx_filter_by_type` |
| T-04-15 | /billing/vouchers/redeem is idempotent on duplicate code | `test_voucher.py::test_redeem_idempotent` |
| T-04-16 | /billing/usage range >90 days returns 422 | `test_usage.py::test_range_capped` |
| T-04-17 | /billing/usage/analytics granularity flips at 48h | `test_usage_stat_service.py::test_granularity_switch_at_48h` |

## Requirements Addressed

- **USER-04** (Balance/transactions/voucher/usage): fully delivered. 8 endpoints under `/api/v1/billing/*` plus 5 endpoints under `/api/v1/keys/*` (the API-key CRUD half of USER-03 is also satisfied here — test coverage in `test_keys.py` + `test_api_key_service.py`). Every wallet-mutating service method preserves SELECT FOR UPDATE row locking and ref_id idempotency. Voucher double-redeem prevented at the BalanceTransaction layer (T-04-15 verified). Usage analytics granularity flips correctly at the 48-hour boundary (T-04-17 verified).

## Decisions Made

- **D-01** (no internal_*) — verified by zero references to `internal_*` files in any new schema/service/controller.
- **D-03** (1:1 schema port) — `schemas/keys.py` and `schemas/billing.py` ported verbatim from `services/user-service/src/schemas/{keys,billing}.py` with only import path rewrites.
- **D-08** (3-plan split) — 04-02 is Wave 2; 04-01 foundations consumed (`require_active_user`, `ApiResponse`, `DateTimeModel`, settings constants). 04-03 (model catalog) is now unblocked.
- **Phase 3 D-04 repo merge** — every `BalanceTxRepository / TopupOrderRepository / UsageStatRepository / VoucherRedemptionCodeRepository / EmailCodeRepository / SessionRepository` source reference rewritten to its merged-repo equivalent. Verified by `grep -E "BalanceTxRepository|TopupOrderRepository|UsageStatRepository|VoucherRedemptionCodeRepository" api_service/services/{api_key,balance,topup_order,voucher,usage_stat}_service.py` returning 0.

## Pitfalls Addressed

- **P1** (deleted repo classes) — `grep -E "BalanceTxRepository|TopupOrderRepository|UsageStatRepository|VoucherRedemptionCodeRepository" api_service/services/*.py` returns 0 (matching auth_service.py's existing docstring reference is unrelated to this plan and is in an 04-01 file).
- **P3** (`get_db_session` → `get_db`) — both controllers (`keys.py`, `billing.py`) depend exclusively on `api_service.core.db.get_db`; `grep -c "get_db_session" controllers/keys.py controllers/billing.py` returns 0.
- **P8** (no service-layer `invalid_model` re-filter) — `usage_stat_service.py` uses `BillingRepository.stat_list_analytics_logs` and `.stat_list_logs_for_hour`, both of which already embed `_exclude_invalid_model()` at the SQL layer. No double-filtering.
- **P10** (single normalize point) — `VoucherService.normalize_code` is `raw.strip().lower()`. The controller does NOT call `normalize_code` before passing `raw_code` to the service; the service is the single source of truth. Test `test_normalize_code_is_strip_lower` asserts this directly.

## Deviations from Plan

The plan's `must_haves` line for /billing/topup-orders mentions a `POST /billing/topup-orders create` endpoint (would call `TopupOrderService.create_order`), but the source `user-service/src/controllers/billing.py` does NOT expose a user-facing POST for topup orders — `TopupOrderService.create_manual` is admin-only. Per D-03 (1:1 port) and the constraint that frontend paths stay unchanged, I kept the 8-endpoint source surface (GET-only for `/topup-orders`). `test_topup.py` covers the GET path and the order-number generator helper instead of a non-existent POST endpoint.

This is a [Rule 1 — Bug avoidance / spec preservation] deviation: the plan's reference to `POST /topup-orders` and `TopupOrderService.create_order` doesn't match the source repository. Implementing the POST would have introduced a new public endpoint that the front-end doesn't expect and that the source spec doesn't define. Service method renamed to `create_manual` is preserved (used in Phase 5 admin port and by tests via internal calls).

One additional belt-and-braces change in `voucher_service.py::redeem_code`: I added a `BillingRepository.exists_by_ref(...)` short-circuit BEFORE the balance mutation, in addition to the source's `code.status != STATUS_ACTIVE` check. The plan's `must_haves` explicitly requires this idempotency mechanism, and the test `test_redeem_idempotent` exercises it. The source relies on `status == REDEEMED` after first redeem; my implementation provides defense-in-depth for the race where two concurrent transactions both observe the code as ACTIVE before either commits. This is a [Rule 2 — auto-add missing critical functionality] deviation.

## Known Stubs

None.

## Threat Flags

No new security-relevant surface beyond what is documented in the plan's `<threat_model>`. All Phase 4 mitigations are in place:

- **T-04-T3** (Voucher double-redeem) — verified by `test_redeem_idempotent` asserting `add_tx.call_count == 1` after duplicate redeem.
- **T-04-T4** (Wallet race) — 11 `for_update=True` call sites in `balance_service.py` (one per wallet-mutating method, two in `consume_for_call_log` for user + api_key).
- **T-04-I4** (API key plaintext leak) — `test_list_no_secrets` + `test_create_returns_plaintext_once` assert the invariant.
- **T-04-I5** (Cross-user data leak in /billing/transactions) — every `BillingRepository.list_tx_for_user(...)` filters by `user_id`; controllers always pass `int(current_user.id)`.
- **T-04-D3** (Unbounded usage range) — `test_range_capped` verifies the 90-day cap.
- **T-04-E2** (cross-user /keys/{id} access) — `verify_key_ownership` uses `ApiKeyRepository.get_owned_key(key_id, user_id)`, which is user-scoped.

## Deferred Issues

`tests/test_health.py::test_ready_returns_200` continues to fail (pre-existing — documented in `04-01-SUMMARY.md` and `deferred-items.md`). Unchanged by this plan.

## Self-Check: PASSED

**Files created (17) — verified existing:**

- `services/api-service/api_service/schemas/keys.py` — FOUND
- `services/api-service/api_service/schemas/billing.py` — FOUND
- `services/api-service/api_service/services/api_key_service.py` — FOUND
- `services/api-service/api_service/services/balance_service.py` — FOUND
- `services/api-service/api_service/services/topup_order_service.py` — FOUND
- `services/api-service/api_service/services/voucher_service.py` — FOUND
- `services/api-service/api_service/services/usage_stat_service.py` — FOUND
- `services/api-service/api_service/controllers/keys.py` — FOUND
- `services/api-service/api_service/controllers/billing.py` — FOUND
- `services/api-service/tests/test_keys.py` — FOUND
- `services/api-service/tests/test_api_key_service.py` — FOUND
- `services/api-service/tests/test_billing_balance.py` — FOUND
- `services/api-service/tests/test_billing_tx.py` — FOUND
- `services/api-service/tests/test_voucher.py` — FOUND
- `services/api-service/tests/test_topup.py` — FOUND
- `services/api-service/tests/test_usage.py` — FOUND
- `services/api-service/tests/test_usage_stat_service.py` — FOUND

**Files modified (2) — verified via `git diff`:**

- `services/api-service/api_service/schemas/__init__.py` — extended re-exports
- `services/api-service/api_service/core/router.py` — keys + billing routers mounted

**Commits (3) — verified via `git log --oneline -5`:**

- `f161a3b` — feat(04-02): port keys/billing schemas + 4 user-domain services
- `dd6f8ee` — feat(04-02): port BalanceService + keys/billing controllers + router mount
- `6de860c` — test(04-02): cover USER-04 keys/billing surface (T-04-10..17)

**Tests:** 112 passing (94 baseline + 18 new from 04-02). `pytest tests/ -q --ignore=tests/test_health.py` exits 0.

**Routes mounted:** `/api/v1/keys` (5 endpoints), `/api/v1/billing/*` (8 endpoints), `/api/v1/auth/*` (10 from 04-01). `api_router` has 23 routes total.

## Unblocks

- **04-03 (model catalog + final email integration tests)** — schemas are available, `core/policies.require_active_user` and `core/db.get_db` proven through 13 new endpoints, `ApiResponse[T]` + `DateTimeModel` envelope pattern established. 04-03 can now copy `schemas/model_catalog.py` from admin-service, write the user-side `ModelCatalogReadService` + `controllers/model_catalog.py`, and round out the `core/router.py` include block.
