---
phase: 04-user-domain-controllers
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - services/api-service/api_service/common/utils/api_key_policy.py
  - services/api-service/api_service/common/utils/email.py
  - services/api-service/api_service/common/utils/password_policy.py
  - services/api-service/api_service/controllers/auth.py
  - services/api-service/api_service/controllers/billing.py
  - services/api-service/api_service/controllers/keys.py
  - services/api-service/api_service/controllers/model_catalog.py
  - services/api-service/api_service/core/arq_pool.py
  - services/api-service/api_service/core/config.py
  - services/api-service/api_service/core/jobs.py
  - services/api-service/api_service/core/policies.py
  - services/api-service/api_service/core/router.py
  - services/api-service/api_service/core/worker.py
  - services/api-service/api_service/main.py
  - services/api-service/api_service/schemas/auth.py
  - services/api-service/api_service/schemas/billing.py
  - services/api-service/api_service/schemas/common.py
  - services/api-service/api_service/schemas/keys.py
  - services/api-service/api_service/schemas/model_catalog.py
  - services/api-service/api_service/services/api_key_service.py
  - services/api-service/api_service/services/auth_service.py
  - services/api-service/api_service/services/balance_service.py
  - services/api-service/api_service/services/email_service.py
  - services/api-service/api_service/services/model_catalog_service.py
  - services/api-service/api_service/services/topup_order_service.py
  - services/api-service/api_service/services/usage_stat_service.py
  - services/api-service/api_service/services/voucher_service.py
findings:
  critical: 3
  warning: 9
  info: 6
  total: 18
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-05-19
**Depth:** standard
**Files Reviewed:** 28 source files (controllers, services, schemas, core, utils)
**Status:** issues_found

## Summary

Phase 4 ports the user-domain stack from `user-service` into `api-service` (auth + keys + billing + model-catalog). The critical security invariants of the migration largely hold: `key_hash` never leaves the service (responses expose `key_prefix` only), `user_id` is consistently filtered from public responses (only `uid` returned), wallet mutations consistently acquire `SELECT … FOR UPDATE` row locks before mutation, and ref_id idempotency is honoured. Email send is correctly deferred to ARQ (D-02). Tests provide solid coverage of the security boundaries.

That said, three blocker-tier defects exist that the existing tests do not catch:

1. **Unverified-email accounts can complete `/auth/register` and immediately log in.** `AuthService.register` writes `status=1` and `email_verified_at=now()` without consuming the verification code — it only takes the code's `get_valid_code_or_raise` lock but never verifies the code was actually issued for that email (it does; just not asserting purpose validity on the same row across retries). Worse, the bcrypt 72-byte limit is enforced only on `LoginRequest`, not on registration/change/reset — a long multi-byte password is silently mishandled.
2. **`/auth/logout` swallows all non-`SessionNotFoundException` exceptions and reports 200 success** (the broad `except Exception:` block at line 243-244 logs but does not re-raise). A user whose DB connection failed mid-logout still sees a "logged out" response while the session row remains active.
3. **The cookie clearing on `/auth/refresh` token failure is non-deterministic against client JS** because `_clear_auth_cookies` uses the `same-site=strict` default — but only when the `JWT_SECRET_KEY` lifecycle is intact. A more subtle issue: when `refresh_access_token` raises mid-execution after the session row's `refresh_token_hash` and `expires_at` have been updated but before `db.commit()`, the rotation is silently rolled back, but `_clear_auth_cookies` clears the client's cookies anyway — leaving the user logged out client-side but still holding an active server-side session.

Beyond the blockers, the wallet-mutation surface has subtle locking-order issues (acquire-lock-before-idempotency-check in `freeze`/`settle`/`refund`), missing topup amount bounds checks (`MIN_TOPUP_AMOUNT`/`MAX_TOPUP_AMOUNT` declared in config.py but never referenced anywhere), and a credentials-leak risk through `register_obj.client.host` taking the first proxy hop instead of `X-Forwarded-For`. Several Pydantic schemas use weak typing (`AuthErrorResponse.code: int = 400` as a default rather than a constraint) and `ApiKeyUpdateRequest.quota_limit` uses `gt=0` which prevents legitimate "lift the limit" updates.

## Critical Issues

### CR-01: Logout endpoint silently succeeds when backend errors occur, leaving session active

**File:** `services/api-service/api_service/controllers/auth.py:237-247`
**Issue:** The outer `try`/`except Exception:` block catches every exception from `AuthService.logout` (including database connection failures, integrity errors, deadlocks) and merely logs them via `logger.exception`, then proceeds to clear cookies and return HTTP 200. The user sees "登出成功" while their refresh-token session row remains active in the database. Anyone with the cookie value (e.g., from a previously logged copy of headers) can still call `/auth/refresh` until the token's natural expiry.

```python
async def logout(...):
    try:
        if refresh_token:
            try:
                await AuthService.logout(db, refresh_token)
            except SessionNotFoundException:
                pass
    except Exception:
        logger.exception("用户登出失败")  # NO re-raise

    _clear_auth_cookies(response)
    return LogoutResponse(code=200, message="登出成功")
```

This is a security regression: the user is told they're safe when they may not be. The source code in user-service may have had the same pattern; that doesn't make it correct.

**Fix:** Re-raise non-Session exceptions so the global exception handler returns the actual error (HTTP 5xx) instead of falsely reporting success:

```python
async def logout(...):
    if refresh_token:
        try:
            await AuthService.logout(db, refresh_token)
        except SessionNotFoundException:
            pass  # Already logged out / session cleaned — OK
        # All other exceptions propagate to global exception handler
    _clear_auth_cookies(response)
    return LogoutResponse(code=200, message="登出成功")
```

If swallowing is intentional for resilience reasons, document the rationale and return an explicit body field indicating the server-side revocation status.

---

### CR-02: Refresh-token rotation has TOCTOU window — exception after partial update clears client cookies but rolls back DB

**File:** `services/api-service/api_service/services/auth_service.py:243-247` and `services/api-service/api_service/controllers/auth.py:264-272`
**Issue:** In `AuthService.refresh_access_token`, the code mutates `session.token_jti`, `session.refresh_token_hash`, and `session.expires_at` **before** `await db.commit()`. If any awaitable in between (e.g., `hash_password_async`) raises, the session row's mutations are rolled back by SQLAlchemy's autorollback. The controller's `except Exception: _clear_auth_cookies(response); raise` then clears the user's cookies. Result: the user is locked out client-side, but their original refresh token (and session row) remain valid on the server — anyone replaying the captured cookie can still successfully refresh.

```python
# auth_service.py:244-247
session.token_jti = get_token_jti(new_refresh_token)
session.refresh_token_hash = await hash_password_async(new_refresh_token)  # <-- can raise
session.expires_at = now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
await db.commit()
```

And:

```python
# auth.py:264-272
try:
    new_access_token, new_refresh_token = await AuthService.refresh_access_token(db, refresh_token)
except Exception:
    _clear_auth_cookies(response)  # <-- clears client cookies even though server-side session is unchanged
    raise
```

**Fix:** Either (a) revoke the old session row explicitly on failure (so the server side also forgets the credential) or (b) do not clear cookies on exception. Option (a) is safer:

```python
# In refresh_access_token, wrap the mutation block:
try:
    session.token_jti = ...
    session.refresh_token_hash = await hash_password_async(new_refresh_token)
    session.expires_at = ...
    await db.commit()
except Exception:
    user_repo.revoke_session(session)
    await db.commit()
    raise
```

Or replace the controller's blanket `_clear_auth_cookies` on exception with explicit logic: only clear when the exception is `SessionRevokedException`/`SessionExpiredException`/`InvalidTokenException`.

---

### CR-03: ARQ pool init/access is process-global and not multi-worker safe; readiness probe does not check it

**File:** `services/api-service/api_service/core/arq_pool.py:16-56` and `services/api-service/api_service/main.py:196-220`
**Issue:** `_arq_pool` is a module-level singleton. `init_arq_pool` is called from `main.py` lifespan startup. However:

1. **`get_arq_pool()` raises `RuntimeError` if called before init.** This means any caller of `EmailService.send_verification_code` during the brief window between worker fork and lifespan startup will receive a 500 error claiming `"ARQ pool not initialised — call init_arq_pool() first"` exposed in the response (depending on the global exception handler). This is a startup-race vulnerability: a request hitting `/auth/send-email-code` before lifespan finishes triggers an uncaught `RuntimeError`.
2. **`/ready` does not include ARQ pool health.** The readiness probe checks DB + Redis db/0 + Cache Redis db/2, but not the ARQ Redis db/1 pool. If db/1 is unreachable, `/auth/send-email-code` will hang or fail at first request post-startup, but Kubernetes/load-balancer probes will still mark the pod ready.
3. The arq pool's underlying connection has no idle-timeout/reconnect handling visible here — if the Redis connection is dropped (network blip, Redis restart), the next `enqueue_job` call will hang or fail without automatic recovery.

**Fix:** (a) catch `RuntimeError` in `EmailService.send_verification_code` and convert to `ServiceUnavailableException`; (b) add `check_arq_pool_ready` to `/ready`; (c) verify the underlying `ArqRedis.enqueue_job` handles reconnects (test by killing Redis between calls).

```python
# In email_service.py:
try:
    pool = get_arq_pool()
    await pool.enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, email, code, purpose)
except (RuntimeError, redis.ConnectionError) as exc:
    log_event(logger, logging.ERROR, "arqEnqueueFailed", email=email, error=str(exc))
    raise ServiceUnavailableException(detail="邮件服务暂时不可用") from exc
```

## Warnings

### WR-01: `register`/`change-password`/`reset-password` schemas enforce `max_length=72` characters, not 72 bytes — silent bcrypt truncation possible

**File:** `services/api-service/api_service/schemas/auth.py:18,123-126,194-200`
**Issue:** `RegisterRequest.password`, `ChangePasswordRequest.new_password`, and `ResetPasswordRequest.new_password` all use `max_length=72` which counts Pydantic string characters, not UTF-8 bytes. A 72-character Chinese password is 216 bytes — bcrypt silently truncates or raises depending on backend version. Only `LoginRequest` has a `validate_password_bytes` validator that checks `len(value.encode("utf-8")) > 72`.

This means a user can register with a password that bcrypt cannot fully hash, then fail every subsequent login because the bytes-trimmed hash does not match the bytes-trimmed login attempt either (or worse, two different long Chinese passwords share the same effective bcrypt-truncated hash).

**Fix:** Add `validate_password_bytes` to all four request schemas (register, login, change, reset). Better still, lift the check into `password_policy.check_password_strength` so it runs everywhere automatically.

```python
@field_validator("password", "new_password")  # or model_validator(mode="after")
@classmethod
def validate_password_bytes(cls, value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 bytes (bcrypt limit)")
    return value
```

---

### WR-02: `confirm_password` validator relies on `info.data["password"]` which is not guaranteed populated when password fails its own validation

**File:** `services/api-service/api_service/schemas/auth.py:36-41`
**Issue:** Pydantic v2 populates `info.data` with values from previously validated fields **in declaration order**, but only if those fields validated successfully. If `password` itself fails its `min_length=8` check, `info.data["password"]` will not be present and `validate_password_match` silently accepts any `confirm_password` value. This means the error message returned to the user only mentions the password issue, not the mismatch — confusing UX but also a TOCTOU-ish issue where the user could exploit a different validator to bypass the match check.

**Fix:** Either use `model_validator(mode="after")` to run after all fields are validated:

```python
@model_validator(mode="after")
def validate_password_match(self):
    if self.password != self.confirm_password:
        raise ValueError("Passwords do not match")
    return self
```

This also lets you remove the `confirm_password` field entirely from the validator since both are accessible as `self.*`.

---

### WR-03: Wallet locking order in `freeze`/`settle`/`refund` acquires user FOR UPDATE before idempotency check

**File:** `services/api-service/api_service/services/balance_service.py:97-115,141-163,216-227`
**Issue:** `freeze`, `settle`, and `refund` all call `_get_user(for_update=True)` **before** `_transaction_exists(...)`. When the same idempotent request hits twice (legit retry or duplicate webhook), the second call:

1. Acquires the user-row FOR UPDATE lock,
2. Discovers the transaction already exists,
3. Returns without committing — but the row lock is still held until the request lifecycle ends.

Compare with `consume_for_call_log` (line 55-65), which does the idempotency check first and only locks the user if mutation is actually needed. The asymmetry is preserved from source, but at the merged-service scale it amplifies lock contention (per the project's own PITFALLS.md note about merged-service lock pressure).

**Fix:** Move the idempotency check before the user lock acquisition in `freeze`/`settle`/`refund`:

```python
async def freeze(...):
    if amount <= 0:
        raise ValidationException(detail="冻结金额必须大于 0")

    if await BalanceService._transaction_exists(db, tx_type=..., ref_type=..., ref_id=request_id):
        return  # No lock needed for idempotent return path

    user = await BalanceService._get_user(db, user_id, for_update=True)
    ...
```

---

### WR-04: `MIN_TOPUP_AMOUNT`/`MAX_TOPUP_AMOUNT` declared in config but never referenced anywhere

**File:** `services/api-service/api_service/core/config.py:58-59` and `services/api-service/api_service/services/topup_order_service.py:23-56`, `services/api-service/api_service/services/balance_service.py:248-288`
**Issue:** Settings `MIN_TOPUP_AMOUNT = 1_000_000` and `MAX_TOPUP_AMOUNT = 10_000_000_000` are declared but never enforced. `TopupOrderService.create_manual` only checks `amount <= 0`. `BalanceService.topup` makes no amount-range check either. If/when an admin topup endpoint lands in Phase 5, it will need explicit upstream validation.

This is dead config — either remove the settings or wire them through. The risk: forgetting to wire them means an admin tool could create a 100 trillion yuan topup, or a 1-cent topup that bypasses platform minimums.

**Fix:** Either remove the settings or enforce them in `create_manual`:

```python
async def create_manual(db, user_id, amount, ...):
    if amount < settings.MIN_TOPUP_AMOUNT:
        raise ValidationException(detail=f"充值金额必须大于等于 {settings.MIN_TOPUP_AMOUNT}")
    if amount > settings.MAX_TOPUP_AMOUNT:
        raise ValidationException(detail=f"充值金额不能超过 {settings.MAX_TOPUP_AMOUNT}")
    ...
```

---

### WR-05: `ApiKeyUpdateRequest.quota_limit` uses `gt=0`, blocking valid "remove limit" updates

**File:** `services/api-service/api_service/schemas/keys.py:64`
**Issue:** `quota_limit: Optional[int] = Field(default=None, gt=0)` forbids zero. Combined with `ApiKeyService.update` line 96-99:

```python
if "quota_limit" in provided_fields and new_quota_limit is not None:
    if api_key.quota_mode != UserApiKey.MODE_LIMITED or new_quota_limit <= 0:
        raise ValidationException(detail="仅限额模式支持更新 quota_limit")
```

A user who wants to switch a LIMITED key back to "no specific limit" (e.g., 0) cannot do so — the schema rejects 0 before the service sees it. The service-layer check then duplicates the same constraint redundantly.

Also note: `ApiKeyCreateRequest.quota_limit` uses `ge=0` (allows 0), but `ApiKeyUpdateRequest.quota_limit` uses `gt=0` (forbids 0) — inconsistent semantics for the same field.

**Fix:** Use `ge=0` on update to match create, and let the service layer be the single enforcement point:

```python
quota_limit: Optional[int] = Field(default=None, ge=0)
```

---

### WR-06: `request.client.host` taken raw without considering X-Forwarded-For — IP logging is reverse-proxy-broken

**File:** `services/api-service/api_service/controllers/auth.py:114,153,196`
**Issue:** Every auth controller does `ip_address = request_obj.client.host if request_obj and request_obj.client else None`. When the api-service is deployed behind nginx/Caddy/CloudFront, `request.client.host` is the proxy's IP, not the user's. This means:

1. Login failures are attributed to the proxy IP, not the attacker.
2. `last_login_ip` is useless for security audit.
3. The IP-allowlist policy on `UserApiKey.allow_ips` (used in `is_ip_allowed`) — although in a different code path — assumes the same `client.host` extraction, so it can be trivially bypassed if api-service is fronted by a proxy: the user's allow-list will never match the proxy IP, blocking all legitimate traffic, OR the user adds the proxy IP, allowing everyone.

**Fix:** Extract IP from `X-Forwarded-For` chain (left-most) with fallback to `X-Real-IP` and finally `client.host`. Use a centralized helper:

```python
def get_client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)
```

This needs corresponding documentation that the reverse proxy must set `X-Forwarded-For` correctly (and strip incoming spoofed values).

---

### WR-07: Model catalog endpoints declare no `response_model` — OpenAPI documentation is empty, no runtime schema validation

**File:** `services/api-service/api_service/controllers/model_catalog.py:30-96`
**Issue:** All four endpoints return `JSONResponse(content=payload)` with no `response_model=...`. As a result:

1. OpenAPI/Swagger docs (`/docs` when DEBUG) show no response schema for `/model-vendors`, `/models`, `/models/categories`, `/models/{slug}`.
2. There is no runtime guarantee that the cached payload still conforms to the schema — if the cache layer ever returns a stale shape (Phase 5 admin writes invalidate via Redis pubsub or TTL), it ships unchanged to the client.
3. The dict-based cache approach bypasses the `DateTimeModel.serialize_model` ISO datetime serializer in `schemas/common.py:18-26` — datetimes in the cache (since `cache_get_or_fetch` stores `model_dump()` output) may have whichever serialization the dump format defaulted to.

Although source did this same way, the code comment "Endpoint paths and behaviour stay identical" overstates correctness if the cache layer produces drift.

**Fix:** Declare `response_model` and return the dict — FastAPI will validate. Better: return the Pydantic model and let FastAPI serialize:

```python
@router.get("/model-vendors", response_model=ApiResponse[PaginatedResponse[ModelVendorItem]])
async def list_model_vendors(...) -> dict:
    payload = await ModelCatalogReadService.list_vendors(...)
    return {"code": 200, "message": "success", "data": payload}
```

(Adjust the cache layer to store envelope-less inner data, then wrap on the way out.)

---

### WR-08: `verify_email` does not check `is_login_locked` or other account-state restrictions; allows reactivating any email-pending account

**File:** `services/api-service/api_service/services/auth_service.py:261-278`
**Issue:** `verify_email` flow:

1. Validates the verification code (which has its own locked_until protection).
2. If `user.status == 0` (disabled), raises `UserDisabledException`.
3. If `user.status == 2` (pending), flips to status `1` (active).
4. Does NOT check `is_login_locked` — a user who has been login-rate-limited and whose code has been somehow obtained (e.g., social engineering) can still successfully verify their email.

This is also a potential audit-trail gap: there's no `log_event` for this status transition. If `status == 2 → 1` is a sensitive privilege escalation, it should be logged.

Additionally, `user.status` magic numbers (0/1/2) are not enumerated anywhere in the schema — the comment in `UserData.status: int = Field(..., description="Status")` says nothing about meaning. A misconfigured client could treat `2` (pending) as `1` (active).

**Fix:** (a) log the status transition; (b) define an enum/IntEnum in `models/user.py` for `STATUS_DISABLED=0`, `STATUS_ACTIVE=1`, `STATUS_PENDING=2` and use it everywhere (controllers, services, schemas docstring).

```python
if user.status == User.STATUS_PENDING:
    user.status = User.STATUS_ACTIVE
    log_event(logger, logging.INFO, "userEmailVerified", uid=user.uid)
user.email_verified_at = now()
```

---

### WR-09: `_DUMMY_HASH` is initialized lazily without thread/async safety — first concurrent login attempts compute it multiple times

**File:** `services/api-service/api_service/services/auth_service.py:58-66`
**Issue:** `_get_dummy_hash()` uses the standard double-checked-init pattern but without a lock. Under load, the first N concurrent login attempts where the user does NOT exist will each compute `hash_password("dummy-timing-equalizer")` from scratch (bcrypt — slow, by design). This is also a CPU-time leak that defeats the timing-equalization goal: the first attacker sees significantly slower responses than later ones.

Less critical: the constant string `"dummy-timing-equalizer"` is the same for every install, so an attacker who can observe response timing of a single non-existent email can characterise the bcrypt-hashing cost on the deployed server, then subtract it to back out actual user-existence signals.

**Fix:** Pre-compute the hash at module import time (or in lifespan startup), OR use `asyncio.Lock`/`functools.cache` properly:

```python
_DUMMY_HASH: str = hash_password("dummy-timing-equalizer")  # module-level constant

def _get_dummy_hash() -> str:
    return _DUMMY_HASH
```

Then sprinkle the per-install salt into the dummy seed so it differs across deployments.

## Info

### IN-01: `Request = None` default in auth controller is an anti-pattern

**File:** `services/api-service/api_service/controllers/auth.py:111,150,193`
**Issue:** `request_obj: Request = None` works because FastAPI special-cases `Request`/`Response` types, but it's confusing — readers may think this is an optional Body parameter. Prefer:

```python
request_obj: Request,
```

(no default) — FastAPI injects unconditionally. If you really need the `None` fallback for testing, use `Optional[Request] = None` and rely on FastAPI's automatic injection still working.

---

### IN-02: `_clear_auth_cookies` doesn't use `delete_cookie(... max_age=0)` and may not be reliable for cross-subdomain setups

**File:** `services/api-service/api_service/controllers/auth.py:89-97`
**Issue:** `response.delete_cookie` sets `Max-Age=0` but the path/domain must match exactly. The current code passes `path=USER_COOKIE_PATH="/"` which is fine for the default deployment, but if `COOKIE_DOMAIN` is ever set on `set_cookie` (it's not currently — see lines 68-86), the delete won't match. Document this invariant explicitly: "If COOKIE_DOMAIN is added later, _clear_auth_cookies must mirror it."

---

### IN-03: `_build_redis_settings` duplicated in `core/arq_pool.py` and `core/jobs.py`

**File:** `services/api-service/api_service/core/arq_pool.py:19-33` and `services/api-service/api_service/core/jobs.py:35-49`
**Issue:** The same Redis settings builder is duplicated. Extract to a shared helper:

```python
# api_service/core/redis_settings.py
def build_arq_redis_settings(redis_url: str = None) -> RedisSettings: ...
```

Both modules then import from this one source.

---

### IN-04: `_JOB_SEND_VERIFICATION_EMAIL` literal duplicated in `email_service.py` and `core/jobs.py`

**File:** `services/api-service/api_service/services/email_service.py:42` and `services/api-service/api_service/core/jobs.py:32`
**Issue:** Both modules define `_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"` with comments warning each other. This is a Pitfall 9 cross-module invariant that the linter cannot catch. Move to a shared constants module:

```python
# api_service/core/job_names.py
JOB_SEND_VERIFICATION_EMAIL: Final[str] = "send_verification_email"
```

Then both producer and consumer reference the same symbol.

---

### IN-05: Hardcoded magic 90-day billing range, no constant for `MAX_BILLING_RANGE_DAYS` in config

**File:** `services/api-service/api_service/controllers/billing.py:39-40`
**Issue:** `MAX_BILLING_RANGE_DAYS = 90` is a module-level constant in the controller. Consider moving to `core/config.py` for visibility — admins may want to tune it per deployment. Same for `DEFAULT_BILLING_LOOKBACK_DAYS = 30`.

---

### IN-06: `Pitfall 7` workaround comment in `schemas/common.py` warns against lint cleanup but the warning is fragile

**File:** `services/api-service/api_service/schemas/common.py:21-23`
**Issue:** The comment says "iterate over list(data.items()) copy so that mutating data[key] does not invalidate the iterator. Do NOT lint-clean." This is a real concern, but the protective measure is only a comment — a future contributor running an autofix tool may "simplify" `list(data.items())` to `data.items()` and break datetime serialization silently.

Two stronger options: (a) write a unit test that detects the regression (iterate without copy, mutate, assert), and (b) restructure to build a new dict rather than mutate in place:

```python
@model_serializer(mode="wrap")
def serialize_model(self, handler):
    data = handler(self)
    return {
        key: format_iso(value) if isinstance(value, datetime) else value
        for key, value in data.items()
    }
```

Cleaner and the iterator issue disappears.

---

_Reviewed: 2026-05-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
