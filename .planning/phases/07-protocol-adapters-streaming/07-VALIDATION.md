---
phase: 7
slug: protocol-adapters-streaming
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | services/api-service/pyproject.toml [tool.pytest.ini_options] |
| **Quick run command** | `cd services/api-service && python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `cd services/api-service && python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd services/api-service && python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `cd services/api-service && python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | RELAY-01 | — | N/A | unit | `pytest tests/relay/test_openai_chat_adapter.py` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | RELAY-11 | — | N/A | unit | `pytest tests/relay/test_sse_streaming.py` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | RELAY-02 | — | N/A | unit | `pytest tests/relay/test_anthropic_adapter.py` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | RELAY-03 | — | N/A | unit | `pytest tests/relay/test_responses_adapter.py` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | RELAY-12 | — | Rate limit rejects excess with 429 | unit | `pytest tests/relay/test_rate_limiter.py` | ❌ W0 | ⬜ pending |
| 07-03-02 | 03 | 2 | RELAY-04 | — | N/A | unit | `pytest tests/relay/test_models_endpoint.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/relay/test_openai_chat_adapter.py` — stubs for RELAY-01, RELAY-11
- [ ] `tests/relay/test_anthropic_adapter.py` — stubs for RELAY-02
- [ ] `tests/relay/test_responses_adapter.py` — stubs for RELAY-03
- [ ] `tests/relay/test_rate_limiter.py` — stubs for RELAY-12
- [ ] `tests/relay/test_models_endpoint.py` — stubs for RELAY-04
- [ ] `tests/relay/conftest.py` — shared fixtures (mock SDK clients, mock Redis)

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE streaming renders correctly in client | RELAY-11 | Requires real HTTP client observing chunked transfer | Use `curl --no-buffer` against running server |
| Rate limit 429 includes Retry-After header | RELAY-12 | Header format validation | `curl -v` and inspect response headers |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
