# Testing Patterns

**Analysis Date:** 2026-05-20

## Test Framework

**Runner:**
- pytest >= 8.0.0
- Config: `services/api-service/pyproject.toml` `[tool.pytest.ini_options]`

**Async Support:**
- pytest-asyncio >= 0.23.0
- Mode: `asyncio_mode = "auto"` (all async tests auto-detected)
- Loop scope: `asyncio_default_fixture_loop_scope = "function"`

**HTTP Client:**
- httpx `AsyncClient` with `ASGITransport` for in-process testing (no real server)

**Assertion Library:**
- Built-in `assert` statements (pytest native)

**Run Commands:**
```bash
cd services/api-service
pytest                           # Run all tests
pytest tests/ -v                 # Verbose
pytest -m "not slow"             # Skip slow tests
coverage run -m pytest           # With coverage
coverage report                  # View coverage
```

## Test File Organization

**Location:** Separate `tests/` directory at service root (not co-located).

**Naming:**
- Unit tests: `test_{feature}.py` (`test_auth_login.py`, `test_relay_auth.py`)
- Integration tests: `tests/integration/test_{flow}.py`
- Relay-specific: `tests/relay/test_{component}.py`

**Structure:**
```
services/api-service/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Shared fixtures (mock_user, mock_db, etc.)
│   ├── test_auth_login.py            # Unit: auth login endpoint
│   ├── test_auth_register.py         # Unit: auth register endpoint
│   ├── test_admin_pools.py           # Unit: admin pool service
│   ├── test_relay_auth.py            # Unit: relay API key validation
│   ├── test_config_cache.py          # Unit: routing config cache
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── conftest.py               # Real DB + Redis fixtures
│   │   ├── test_relay_e2e.py         # E2E: full relay lifecycle
│   │   ├── test_admin_relay_cache.py # Integration: admin cache ops
│   │   └── test_resource_concurrency.py
│   └── relay/
│       ├── __init__.py
│       ├── conftest.py               # Relay-specific fixtures
│       ├── test_chat_endpoint.py
│       ├── test_anthropic_endpoint.py
│       ├── test_rate_limiter.py
│       ├── test_streaming.py
│       └── test_sdk_clients.py
```

## Test Structure

**Suite Organization — class-based for related tests:**
```python
class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_check_all_global_limit_exceeded(self):
        """Global RPM=1, second call should raise RateLimitExceeded."""
        ...

    @pytest.mark.asyncio
    async def test_check_all_passes_when_under_limit(self):
        """All limits generous - should pass without raising."""
        ...
```

**Function-based for independent tests:**
```python
@pytest.mark.asyncio
@patch("api_service.controllers.auth.AuthService.login", new_callable=AsyncMock)
async def test_login_success(mock_login, client):
    """T-04-03 - login success: 200, sets cookies, returns access_token."""
    ...
```
<!-- TESTING_PART2 -->

**Patterns:**
- Docstrings reference test IDs: `"""T-04-03 - login success: 200, sets cookies."""`
- Arrange-Act-Assert implicit (setup -> call -> assert)
- `autouse=True` fixtures for cache clearing

## Mocking

**Framework:** `unittest.mock` (AsyncMock, MagicMock, patch)

**Patterns — patching service methods at controller level:**
```python
@patch("api_service.controllers.auth.AuthService.login", new_callable=AsyncMock)
async def test_login_success(mock_login, client):
    user = _stub_user()
    mock_login.return_value = (user, "access-token-xyz", "refresh-token-xyz")

    response = await client.post("/api/v1/auth/login", json={...})
    assert response.status_code == 200
```

**Patterns — mocking DB session:**
```python
@pytest.fixture
def mock_db():
    """AsyncMock standing in for AsyncSession."""
    return AsyncMock()
```

**Patterns — mocking Redis:**
```python
@pytest.fixture
def mock_redis():
    """AsyncMock standing in for redis.asyncio.Redis."""
    m = AsyncMock()
    m.register_script = MagicMock(return_value=AsyncMock(return_value=1))
    return m
```

**What to Mock (unit tests):**
- Database sessions (AsyncMock)
- Redis connections (AsyncMock)
- Service layer methods (patch at controller import path)
- External HTTP clients (AsyncMock)

**What NOT to Mock (integration tests):**
- Real MySQL database (eucal_ai_test)
- Real Redis (localhost:6379 db/1 and db/2)
- FastAPI app via ASGITransport

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**
```python
@pytest.fixture
def mock_user():
    """A MagicMock user with stable values for /auth, /keys, /billing tests."""
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.status = 1
    user.email = "test@example.com"
    user.email_verified_at = datetime(2026, 1, 1, 0, 0, 0)
    return user

@pytest.fixture
def mock_admin():
    """Default admin (role=ADMIN, status=ACTIVE)."""
    admin = MagicMock()
    admin.id = 1
    admin.uid = "adm_test01"
    admin.role = AdminRole.ADMIN
    admin.status = AdminStatus.ACTIVE
    return admin
```

**Integration fixtures (`tests/integration/conftest.py`):**
```python
@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create async engine pointing to eucal_ai_test, create all tables."""
    eng = create_async_engine("mysql+aiomysql://root:abc123@localhost:3306/eucal_ai_test")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def db_session(engine):
    """Per-test session with transaction rollback for isolation (D-04)."""
    conn = await engine.connect()
    txn = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    yield session
    await session.close()
    await txn.rollback()
    await conn.close()
```

**ASGI test client fixture:**
```python
@pytest_asyncio.fixture
async def app_client(engine, session_factory, db_session, cache_redis):
    """ASGI test client with dependency overrides for DB and Redis."""
    async def _override_get_db():
        yield db_session
    app.dependency_overrides[_runtime.get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

**Relay test helpers (`tests/relay/conftest.py`):**
```python
def make_test_principal(**overrides) -> ValidatedApiKey:
    """Create a test ValidatedApiKey principal with sensible defaults."""
    defaults = dict(id=1, user_id=1, key_hash="testhash123", status=1, ...)
    defaults.update(overrides)
    return ValidatedApiKey(**defaults)
```

**Location:**
- Shared fixtures: `tests/conftest.py`
- Integration fixtures: `tests/integration/conftest.py`
- Relay fixtures: `tests/relay/conftest.py`

## Coverage

**Requirements:** Not formally enforced in CI (no coverage threshold configured).

**View Coverage:**
```bash
cd services/api-service
coverage run -m pytest tests/
coverage report --show-missing
coverage html  # generates htmlcov/
```

## Test Types

**Unit Tests (majority):**
- Scope: Individual service methods, controller endpoints, utility functions
- Approach: Mock DB/Redis, patch service layer, test via httpx AsyncClient
- Location: `tests/test_*.py`

**Integration Tests:**
- Scope: Full request lifecycle with real DB and Redis
- Approach: Transaction rollback isolation, real ASGITransport
- Location: `tests/integration/`
- Requirements: MySQL (eucal_ai_test), Redis (localhost:6379), inference-service (localhost:8004)

**E2E Tests:**
- Scope: Full relay flow (auth -> route -> forward -> bill -> log)
- Location: `tests/integration/test_relay_e2e.py`
- Tests all 3 protocols: OpenAI Chat, Anthropic Messages, OpenAI Responses

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_something():
    result = await some_async_function()
    assert result == expected
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_login_lockout(mock_login, client):
    mock_login.side_effect = InvalidCredentialsException(detail="账户已被锁定")
    response = await client.post("/api/v1/auth/login", json={...})
    assert response.status_code == 401
```

**Dependency Override Pattern:**
```python
@pytest_asyncio.fixture
async def client():
    async def _override_db():
        yield AsyncMock()
    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

**Environment Setup Pattern (required for pydantic-settings):**
```python
import os
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")
# Must be BEFORE any api_service imports
```

## Test Markers

```python
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]
```

## Notable Gaps

- No formal coverage threshold enforced (target 80% per project rules, not gated)
- Legacy services (`user-service`, `admin-service`, `router-service`) have no test directories
- `inference-service` has no test directory
- No CI/CD pipeline configuration visible in the repository
- Integration tests require external services (MySQL, Redis, inference-service) running locally

---

*Testing analysis: 2026-05-20*
