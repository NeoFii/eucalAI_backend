---
status: partial
phase: 04-user-domain-controllers
source: [04-VERIFICATION.md]
started: 2026-05-19T00:00:00Z
updated: 2026-05-19T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Logout endpoint silently succeeds on backend errors (CR-01 from 04-REVIEW)
expected: When AuthService.logout raises a non-SessionNotFoundException error (DB outage, deadlock, integrity violation), the API should propagate the failure to the client (HTTP 5xx) — not return 200 "logged out" while leaving the session row alive on the server.
result: [pending]

### 2. Refresh-token rotation TOCTOU window — client cookies cleared while server-side session still valid (CR-02 from 04-REVIEW)
expected: If AuthService.refresh_access_token raises mid-execution (e.g. hash_password_async fails after token_jti has been set but before db.commit), the server-side session row should also be revoked — not just rolled back. Otherwise the user is locked out client-side but their captured refresh token still works on the server.
result: [pending]

### 3. ARQ pool readiness probe gap (CR-03 from 04-REVIEW)
expected: /ready should fail when ARQ Redis db/1 is unreachable, because /auth/send-email-code will fail at runtime. Currently /ready only checks DB + Redis db/0 + Cache Redis db/2.
result: [pending]

### 4. Phase 4 endpoint contract matches user-service behavior across all 27 paths under load
expected: Each of the 27 endpoints (10 /auth/* + 5 /keys/* + 8 /billing/* + 4 /models* + /model-vendors) returns the same status code, response envelope, cookie behavior, and error-mapping as the current user-service under realistic traffic.
result: [pending]

### 5. SMTP delivery actually reaches the user mailbox via ARQ worker (USER-06 end-to-end)
expected: POST /auth/send-email-code enqueues the job; the ARQ worker (`arq api_service.core.worker.WorkerSettings`) starts, picks up the job, calls _send_smtp_sync with SMTP credentials from settings, and the recipient receives a 6-digit code email within ~10 seconds.
result: [pending]

### 6. MIN_TOPUP_AMOUNT / MAX_TOPUP_AMOUNT dead config decision (WR-04 from 04-REVIEW)
expected: Decide whether the two settings (declared in config.py:58-59 but never referenced in any service or controller) should be (a) removed from config now, or (b) left for Phase 5 admin-topup endpoint to wire.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
