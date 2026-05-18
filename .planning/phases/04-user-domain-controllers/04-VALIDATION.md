---
phase: 4
slug: user-domain-controllers
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `04-RESEARCH.md` "Validation Architecture" section.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23+ (verified in `services/api-service/pyproject.toml:37-38`) |
| **Config file** | `services/api-service/pyproject.toml` `[tool.pytest.ini_options]` block — Wave 0 must add `asyncio_mode = "auto"` + `asyncio_default_fixture_loop_scope = "function"` |
| **Quick run command** | `cd services/api-service && pytest tests/ -x -q` |
| **Full suite command** | `cd services/api-service && pytest tests/ --cov=api_service --cov-report=term-missing --cov-fail-under=80` |
| **Estimated runtime** | ~10-15 seconds (quick) / ~45-60 seconds (full with coverage) |

---

## Sampling Rate

- **After every task commit:** `cd services/api-service && pytest tests/ -x -q -k "<module>"` — runs only related tests (~1-3s)
- **After every plan wave:** `cd services/api-service && pytest tests/ -x -q` — full quick run (~10-15s)
- **Before `/gsd:verify-work`:** `pytest tests/ --cov=api_service --cov-fail-under=80` must be green
- **Max feedback latency:** 15 seconds (quick) / 60 seconds (full)

---

## Per-Task Verification Map

> Tasks not yet assigned IDs (planner will produce 04-01-NN / 04-02-NN / 04-03-NN). This table will be updated during plan generation. Skeleton derived from `04-RESEARCH.md` § Phase Requirements → Test Map.

| Task ID (TBD) | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-?? | 01 | 0 | USER-01 | T-04-01 | Conftest fixtures + asyncio mode green | infra | `pytest tests/ --collect-only` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-02 | Register persists user + sets HttpOnly cookies + 201 | integration | `pytest tests/test_auth_register.py::test_register_success -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-03 | Login returns access_token + sets HttpOnly+SameSite cookies | integration | `pytest tests/test_auth_login.py::test_login_success -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-04 | Login lockout after N failures (LOGIN_MAX_FAILURES) | integration | `pytest tests/test_auth_login.py::test_login_lockout -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-05 | Logout revokes session row by jti + clears cookies | integration | `pytest tests/test_auth_logout.py::test_logout_revokes_session -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-06 | Refresh rotates both tokens + updates session row | integration | `pytest tests/test_auth_refresh.py::test_refresh_rotates -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-07 | /auth/me excludes user_id, returns user_uid only (D-09: rpm from settings constant) | integration | `pytest tests/test_auth_me.py::test_me_excludes_id -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-08 | change-password revokes all sessions of the user | integration | `pytest tests/test_auth_change.py::test_change_revokes_sessions -x` | ❌ W0 | ⬜ |
| 04-01-?? | 01 | 1 | USER-01 | T-04-09 | password-reset flow via email code | integration | `pytest tests/test_auth_reset.py::test_reset_with_code -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-10 | Create API key returns plaintext once + sha256 hash in DB | integration | `pytest tests/test_keys.py::test_create_returns_plaintext_once -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-11 | List API keys never exposes plaintext or hash | integration | `pytest tests/test_keys.py::test_list_no_secrets -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-12 | Soft-delete sets deleted_at (no row delete) | unit | `pytest tests/test_api_key_service.py::test_delete_is_soft -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-13 | /billing/balance returns int fields + available_balance | integration | `pytest tests/test_billing_balance.py::test_balance_fields -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-14 | /billing/transactions paginates with type filter | integration | `pytest tests/test_billing_tx.py::test_tx_filter_by_type -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-15 | /billing/vouchers/redeem idempotent by ref_id on duplicate code | integration | `pytest tests/test_voucher.py::test_redeem_idempotent -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-16 | /billing/usage time range capped at 90 days | integration | `pytest tests/test_usage.py::test_range_capped -x` | ❌ W0 | ⬜ |
| 04-02-?? | 02 | 2 | USER-04 | T-04-17 | /billing/usage/analytics granularity switches at 48h | unit | `pytest tests/test_usage_stat_service.py::test_granularity_switch -x` | ❌ W0 | ⬜ |
| 04-03-?? | 03 | 3 | USER-05 | T-04-18 | /model-vendors uses Redis cache (second call ≪ first) | integration | `pytest tests/test_model_catalog.py::test_cache_hits -x` | ❌ W0 | ⬜ |
| 04-03-?? | 03 | 3 | USER-05 | T-04-19 | /models filters by vendor + q correctly | integration | `pytest tests/test_model_catalog.py::test_filter -x` | ❌ W0 | ⬜ |
| 04-03-?? | 03 | 3 | USER-05 | T-04-20 | /models/{slug} returns 404 on missing slug | integration | `pytest tests/test_model_catalog.py::test_404 -x` | ❌ W0 | ⬜ |
| 04-03-?? | 03 | 3 | USER-06 | T-04-21 | send-email-code rate-limits to 3/day per email | integration | `pytest tests/test_email_send.py::test_daily_limit -x` | ❌ W0 | ⬜ |
| 04-03-?? | 03 | 3 | USER-06 | T-04-22 | send-email-code enqueues ARQ job (D-02 behavior change verified) | integration | `pytest tests/test_email_send.py::test_enqueues_arq -x` | ❌ W0 | ⬜ |
| 04-03-?? | 03 | 3 | USER-06 | T-04-23 | verify-email increments error_count on bad code, locks after N | integration | `pytest tests/test_email_verify.py::test_error_count -x` | ❌ W0 | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test infrastructure must land **before** any controller/service is ported. The planner MUST place these in 04-01 Wave 0:

- [ ] `services/api-service/pyproject.toml` — add `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `testpaths = ["tests"]`
- [ ] `services/api-service/tests/conftest.py` — shared fixtures:
  - `db_session` — async sqlite-in-memory or MySQL test container session
  - `client` — `httpx.AsyncClient` bound to FastAPI app
  - `arq_pool_mock` — in-memory queue collector (job intercept, no real Redis)
  - `redis_mock` — fakeredis or in-memory cache
  - `auth_user` — registered + logged-in test user fixture
- [ ] `services/api-service/tests/__init__.py` — package marker
- [ ] `services/api-service/tests/test_auth_register.py` — covers USER-01 register path (stub + 1 happy path)
- [ ] `services/api-service/tests/test_auth_login.py` — covers USER-01 login + lockout
- [ ] `services/api-service/tests/test_auth_logout.py` — covers USER-01 logout
- [ ] `services/api-service/tests/test_auth_refresh.py` — covers USER-01 refresh
- [ ] `services/api-service/tests/test_auth_me.py` — covers USER-01 /auth/me (assert no `user_id` field; assert `rpm == settings.DEFAULT_USER_RPM`)
- [ ] `services/api-service/tests/test_auth_change.py` — covers USER-01 change-password + session revoke
- [ ] `services/api-service/tests/test_auth_reset.py` — covers USER-01 password reset via email code
- [ ] `services/api-service/tests/test_keys.py` — covers USER-04 API key endpoints
- [ ] `services/api-service/tests/test_api_key_service.py` — unit tests for ApiKeyService
- [ ] `services/api-service/tests/test_billing_balance.py` — covers USER-04 /billing/balance
- [ ] `services/api-service/tests/test_billing_tx.py` — covers USER-04 /billing/transactions
- [ ] `services/api-service/tests/test_voucher.py` — covers USER-04 voucher redeem idempotency
- [ ] `services/api-service/tests/test_topup.py` — covers USER-04 topup order create + status
- [ ] `services/api-service/tests/test_usage.py` — covers USER-04 /billing/usage
- [ ] `services/api-service/tests/test_usage_stat_service.py` — unit tests for granularity logic
- [ ] `services/api-service/tests/test_model_catalog.py` — covers USER-05 /model-vendors, /models, /models/{slug}
- [ ] `services/api-service/tests/test_email_send.py` — covers USER-06 send + ARQ enqueue assertion
- [ ] `services/api-service/tests/test_email_verify.py` — covers USER-06 verify-email error counting

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SMTP send actually delivers email | USER-06 | Requires live SMTP server + receiving mailbox; CI uses mock mode (`SMTP_HOST=""`) | Configure `SMTP_HOST/USER/PASSWORD` env, register a test account with a real email, check inbox for verification code |
| Cookie `SameSite=strict` survives production reverse proxy | USER-01 | Depends on deployment topology (api-service + frontend on same site); cannot be verified in unit/integration tests | Deploy to staging; open `/auth/login` from frontend; verify refresh cookie sent on subsequent `/auth/refresh` |
| ARQ worker actually picks up `send_verification_email` jobs | USER-06 | Tests assert enqueue happens; verifying the worker dequeue path requires a live ARQ worker process | Run `arq api_service.core.worker.WorkerSettings` locally, hit `/auth/send-email-code`, watch worker logs for `emailSendStart` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all `❌ W0` references above (24 test files + conftest + pytest config)
- [ ] No watch-mode flags (no `pytest-watch`, no `--ff` interactive)
- [ ] Feedback latency < 15s (quick) / < 60s (full)
- [ ] `nyquist_compliant: true` set in frontmatter after planner refines task IDs

**Approval:** pending (planner refines per-task IDs + checker verifies before sign-off)
