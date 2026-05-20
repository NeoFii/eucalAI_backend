# Phase 9: Integration Testing - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 6 (new integration test files to create)
**Analogs found:** 5 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/integration/conftest.py` | config | CRUD | `tests/conftest.py` + `tests/relay/conftest.py` | role-match |
| `tests/integration/test_relay_e2e.py` | test | streaming + request-response | `tests/relay/test_chat_endpoint.py` | exact |
| `tests/integration/test_relay_billing_e2e.py` | test | CRUD | `tests/test_relay_billing.py` | role-match |
| `tests/integration/test_admin_cache_propagation.py` | test | event-driven | `tests/test_config_cache.py` | role-match |
| `tests/integration/test_memory_constraint.py` | test | batch | (none) | no-analog |
| `tests/integration/test_snowflake_concurrency.py` | test | batch | `tests/test_snowflake_worker.py` | role-match |

## Pattern Assignments

### `tests/integration/conftest.py` (config, CRUD)

**Analog:** `tests/conftest.py` (lines 1-133) + `tests/relay/conftest.py` (lines 1-57)

**Environment setup pattern** (conftest.py lines 9-18):
```python
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# Provide reasonable test defaults BEFORE any pydantic-settings model loads.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")
```

**Fixture hierarchy pattern** — root conftest provides shared fixtures, subdirectory conftest adds domain-specific ones:
```python
# Root: mock_user, mock_db, arq_pool_mock, redis_mock, mock_admin, mock_super_admin
# Relay subdir: make_test_principal(), mock_redis, mock_sdk_client_pool, mock_settings
```

**Factory fixture pattern** (test_relay_billing.py lines 31-39):
```python
@pytest.fixture
def mock_session_factory():
    """Mock async session factory (context manager)."""
    session = AsyncMock()
    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory, session
```

**Integration test: real DB session fixture should follow this shape but with real engine:**
```python
# For Phase 9, replace AsyncMock with real async engine:
# - session-scoped: create_async_engine + run Alembic migrations
# - function-scoped: begin transaction, yield session, rollback
```

**Test principal factory** (relay/conftest.py lines 13-30):
```python
def make_test_principal(**overrides) -> ValidatedApiKey:
    """Create a test ValidatedApiKey principal with sensible defaults."""
    defaults = dict(
        id=1, user_id=1, key_hash="testhash123", status=1,
        quota_mode=0, quota_limit=0, quota_used=0,
        allowed_models="", allow_ips=None, expires_at=None,
        user_rpm_limit=60, balance=10000,
    )
    defaults.update(overrides)
    return ValidatedApiKey(**defaults)
```

---

### `tests/integration/test_relay_e2e.py` (test, streaming + request-response)

**Analog:** `tests/relay/test_chat_endpoint.py` + `tests/relay/test_streaming.py`

**ASGI test client pattern** (test_chat_endpoint.py lines 44-79):
```python
@pytest.mark.asyncio
async def test_chat_completions_non_stream():
    """POST /v1/chat/completions non-stream returns valid OpenAI format."""
    from fastapi.responses import JSONResponse

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    principal, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("api_service.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "chat.completion"
```

**Dependency override pattern** (test_chat_endpoint.py lines 28-38):
```python
def _override_auth():
    principal = make_test_principal()
    async def _dep():
        return principal
    return principal, _dep

async def _noop_rate_limit():
    return None
```

**SSE streaming assertion pattern** (test_streaming.py lines 83-94):
```python
assert resp.status_code == 200
assert "text/event-stream" in resp.headers.get("content-type", "")

body = resp.text
lines = [line for line in body.split("\n") if line.strip()]
for line in lines:
    assert line.startswith("data: "), f"Line does not start with 'data: ': {line}"
assert lines[-1] == "data: [DONE]"
for line in lines[:-1]:
    payload = line[len("data: "):]
    parsed = json.loads(payload)
    assert "choices" in parsed
```

**Anthropic SSE format assertion** (test_streaming.py lines 137-146):
```python
assert resp.status_code == 200
assert "text/event-stream" in resp.headers.get("content-type", "")
body = resp.text
assert "event: message_start\n" in body
assert "event: message_stop\n" in body
data_lines = [line for line in body.split("\n") if line.startswith("data: ")]
for line in data_lines:
    payload = line[len("data: "):]
    parsed = json.loads(payload)
    assert "type" in parsed
```

**Responses protocol SSE assertion** (test_responses_endpoint.py lines 121-125):
```python
assert resp.status_code == 200
assert "text/event-stream" in resp.headers.get("content-type", "")
body = resp.text
assert "event: response.created" in body
assert "event: response.completed" in body
```

**Note for Phase 9:** Integration tests should NOT mock `CallLifecycle.execute`. Instead, use real auth (seed API key in DB) and let the full lifecycle run against real inference-service.

---

### `tests/integration/test_relay_billing_e2e.py` (test, CRUD)

**Analog:** `tests/test_relay_billing.py`

**Service method testing pattern** (test_relay_billing.py lines 46-54):
```python
@pytest.mark.asyncio
async def test_get_balance_redis_hit(mock_redis):
    """Redis GET returns value -> return it directly."""
    mock_redis.get.return_value = "5000000"

    balance = await RelayBillingService.get_balance(
        mock_redis, user_id=1, db_session_factory=None
    )
    assert balance == 5_000_000
    mock_redis.get.assert_called_once_with("user:quota:1")
```

**Error case testing pattern** (test_relay_billing.py lines 138-153):
```python
@pytest.mark.asyncio
async def test_pre_consume_insufficient(mock_redis):
    """DECRBY returns negative -> rollback INCRBY + raise InsufficientBalanceError."""
    mock_redis.decrby.return_value = -50_000

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await RelayBillingService.pre_consume(
            mock_redis, user_id=1, estimated_cost=100_000,
            balance=50_000, trust_quota=10_000_000,
        )
    assert exc_info.value.balance == 50_000
    assert exc_info.value.required == 100_000
    mock_redis.incrby.assert_called_once_with("user:quota:1", 100_000)
```

**Note for Phase 9:** Integration billing tests should use real Redis and verify actual balance changes in DB after full relay call completes.

---

### `tests/integration/test_admin_cache_propagation.py` (test, event-driven)

**Analog:** `tests/test_config_cache.py`

**Cache lifecycle testing pattern** (test_config_cache.py lines 91-104):
```python
@pytest.mark.asyncio
async def test_start_success(mock_redis, mock_session_factory):
    """start() populates _cached_config when DB returns valid config."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_valid_config()
        mock_redis.get.return_value = "5"
        await cache.start(mock_session_factory)

    assert cache._cached_config is not None
    assert cache._version == 5
```

**Version bump reload pattern** (test_config_cache.py lines 160-181):
```python
@pytest.mark.asyncio
async def test_check_and_reload_version_bump(mock_redis, mock_session_factory):
    """check_and_reload reloads from DB when version changes."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_valid_config()
        mock_redis.get.return_value = "1"
        await cache.start(mock_session_factory)

    # Simulate version bump
    new_config = _make_valid_config()
    new_config["router_alias"] = "smart"
    mock_redis.get.return_value = "2"

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = new_config
        await cache.check_and_reload(mock_session_factory)
        mock_load.assert_called_once()

    assert cache._version == 2
    assert cache._cached_config["router_alias"] == "smart"
```

**Graceful degradation pattern** (test_config_cache.py lines 184-204):
```python
@pytest.mark.asyncio
async def test_check_and_reload_redis_down(mock_redis, mock_session_factory):
    """check_and_reload gracefully handles Redis failure (fail-open)."""
    # ... start with valid config ...
    mock_redis.get.side_effect = ConnectionError("Redis connection refused")

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        await cache.check_and_reload(mock_session_factory)
        mock_load.assert_not_called()

    # Config should remain unchanged
    assert cache._cached_config == original_config
```

**Note for Phase 9:** Integration tests should call real admin API endpoints to modify routing config, then verify relay behavior changes without mocking `_load_from_db`.

---

### `tests/integration/test_snowflake_concurrency.py` (test, batch)

**Analog:** `tests/test_snowflake_worker.py` (partial match)

**Class-based test organization** (test_channel_selector.py lines 29-39):
```python
class TestChannelSelectorWeightedRR:
    """Descriptive class docstring."""

    def test_select_weighted_round_robin(self):
        selector = ChannelSelector()
        channels = [_make_channel("ch-a", weight=2), _make_channel("ch-b", weight=1)]
        results = [selector.select("model-x", channels)["channel_slug"] for _ in range(3)]
        assert results.count("ch-a") == 2
        assert results.count("ch-b") == 1
```

**Async fixture with cleanup** (test_inference_client.py lines 16-22):
```python
@pytest_asyncio.fixture
async def client():
    """Create client with short timeouts for testing."""
    c = InferenceClient(base_url="http://inference.test", secret="test-secret", timeout=5.0)
    yield c
    await c.close()
```

---

## Shared Patterns

### ASGI Test Client Setup
**Source:** `tests/relay/test_chat_endpoint.py` lines 17-18, 67-68
**Apply to:** All integration test files that hit HTTP endpoints
```python
from httpx import ASGITransport, AsyncClient
from api_service.main import app

transport = ASGITransport(app=app)
async with AsyncClient(transport=transport, base_url="http://test") as client:
    resp = await client.post(...)
```

### Dependency Override + Cleanup
**Source:** `tests/relay/test_chat_endpoint.py` lines 61-74
**Apply to:** All endpoint integration tests (but Phase 9 should minimize overrides — use real deps)
```python
app.dependency_overrides[require_api_key] = auth_dep
app.dependency_overrides[require_rate_limit] = _noop_rate_limit
try:
    # ... test logic ...
finally:
    app.dependency_overrides.clear()
```

### Async Test Marker
**Source:** All test files
**Apply to:** Every async test function
```python
@pytest.mark.asyncio
async def test_something():
    ...
```

### Fire-and-Forget Wait Pattern
**Source:** `tests/test_call_log_writer.py` (implied by asynccontextmanager usage)
**Apply to:** Integration tests that verify call_log DB writes after relay calls
```python
# After relay request completes, wait for background task:
import asyncio
await asyncio.sleep(0.5)  # Let create_task fire-and-forget complete
# Then query DB to verify call_log was written
```

### Error Assertion Pattern
**Source:** `tests/relay/test_streaming.py` lines 184-204
**Apply to:** Rate limit and auth failure integration tests
```python
async def _raise_rate_limit():
    raise RateLimitExceeded("User rate limit exceeded: 60 RPM", retry_after=3)

app.dependency_overrides[require_rate_limit] = _raise_rate_limit
# ... make request ...
assert resp.status_code == 429
```

### Test Data Factory Pattern
**Source:** `tests/test_config_cache.py` lines 44-86
**Apply to:** Integration tests needing routing config seed data
```python
def _make_valid_config() -> dict:
    """Return a minimal valid normalized config dict."""
    return {
        "router_alias": "auto",
        "route_order": [...],
        "model_channels": {"gpt-5-4": [{"channel_slug": "openai:1", ...}]},
        "model_prices": {"gpt-5-4": {"input": 5000000, "output": 15000000}},
        ...
    }
```

### caplog for Warning/Error Verification
**Source:** `tests/test_call_log_writer.py` lines 57-74
**Apply to:** Integration tests verifying graceful degradation logging
```python
@pytest.mark.asyncio
async def test_failure_logs_warning(self, caplog):
    with caplog.at_level(logging.WARNING):
        await some_operation_that_fails()
    assert "expected message" in caplog.text
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/integration/test_memory_constraint.py` | test | batch | No existing tests spawn real uvicorn workers or measure RSS with psutil. This is a novel test pattern for the project. |

**Guidance for planner:** Use subprocess to spawn `uvicorn api_service.main:app --workers 4`, send concurrent requests via httpx, collect RSS via `psutil.Process(pid).memory_info().rss` for each child, assert total < 1.5GB. Mark with `@pytest.mark.slow`.

## Metadata

**Analog search scope:** `services/api-service/tests/` (all subdirectories)
**Files scanned:** 42 test files
**Pattern extraction date:** 2026-05-19
