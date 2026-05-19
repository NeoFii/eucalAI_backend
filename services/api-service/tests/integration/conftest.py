"""Integration test fixtures — real DB (transaction rollback) + real Redis.

Requires:
- MySQL: eucal_ai_test database accessible at localhost:3306
- Redis: localhost:6379 (db/1 for queue, db/2 for cache)
- inference-service: localhost:8004 (for upstream relay calls)

Per-test isolation via transaction rollback (D-04): each test runs inside a
transaction that is rolled back after the test completes.
"""

from __future__ import annotations

import hashlib
import os

# Set env vars BEFORE any pydantic-settings model loads
os.environ["JWT_SECRET_KEY"] = "integration-test-jwt-secret-key-at-least-32-chars"
os.environ["INTERNAL_SECRET"] = "integration-test-internal-secret-at-least-32-chars"
os.environ["DATABASE_URL"] = "mysql+aiomysql://root:password@localhost:3306/eucal_ai_test"
os.environ["CACHE_REDIS_URL"] = "redis://127.0.0.1:6379/2"
os.environ["WORKER_QUEUE_REDIS_URL"] = "redis://127.0.0.1:6379/1"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"
os.environ["INFERENCE_SERVICE_URL"] = "http://127.0.0.1:8004"
os.environ["INFERENCE_SERVICE_SECRET"] = "test-inference-secret-at-least-32-chars"
os.environ["PROVIDER_SECRET_MASTER_KEY"] = "a" * 64  # 64 hex chars = 32 bytes AES-256
os.environ["BOOTSTRAP_SUPERADMIN_ENABLED"] = "false"
os.environ["BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api_service.common.infra.db.base import Base  # noqa: E402
from api_service.common.security.crypto import encrypt_api_key  # noqa: E402
from api_service.models import (  # noqa: E402
    ModelCatalog,
    ModelVendor,
    Pool,
    PoolAccount,
    PoolModelConfig,
    User,
    UserApiKey,
)

TEST_API_KEY_RAW = "sk-test-integration-key"
TEST_API_KEY_HASH = hashlib.sha256(TEST_API_KEY_RAW.encode()).hexdigest()
MASTER_KEY_HEX = "a" * 64


# ══════════════════════════════════════════════════════════════════════════════
# Session-scoped fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create async engine pointing to eucal_ai_test, create all tables."""
    eng = create_async_engine(
        "mysql+aiomysql://root:password@localhost:3306/eucal_ai_test",
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(engine):
    """Async session factory bound to the test engine."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def cache_redis():
    """Real Redis connection to db/2 (cache). Flushed on teardown."""
    r = aioredis.from_url("redis://127.0.0.1:6379/2", decode_responses=True)
    yield r
    await r.flushdb()
    await r.aclose()


@pytest_asyncio.fixture(scope="session")
async def queue_redis():
    """Real Redis connection to db/1 (queue). Flushed on teardown."""
    r = aioredis.from_url("redis://127.0.0.1:6379/1", decode_responses=True)
    yield r
    await r.flushdb()
    await r.aclose()


# ══════════════════════════════════════════════════════════════════════════════
# Function-scoped fixtures (per-test transaction rollback)
# ══════════════════════════════════════════════════════════════════════════════


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


@pytest_asyncio.fixture
async def app_client(db_session, cache_redis):
    """ASGI test client with dependency overrides for DB and Redis."""
    from api_service.core.db import _runtime
    from api_service.common.infra import cache as cache_module
    from api_service.main import app

    # Override get_db to yield our transactional session
    async def _override_get_db():
        yield db_session

    # Store originals
    original_get_cache_redis = cache_module.get_cache_redis
    original_cache_redis = cache_module._cache_redis

    # Override cache redis
    cache_module._cache_redis = cache_redis

    app.dependency_overrides[_runtime.get_db] = _override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(_runtime.get_db, None)
        cache_module._cache_redis = original_cache_redis


# ══════════════════════════════════════════════════════════════════════════════
# Seed fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def seed_user(db_session):
    """Insert a test user with high balance."""
    user = User(
        id=1,
        uid="u_inttest",
        email="inttest@test.com",
        password_hash="$2b$12$dummyhashforintegrationtesting",
        balance=1_000_000_000,  # 1000 yuan in micro-units
        status=1,
        rpm_limit=60,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def seed_api_key(db_session, seed_user):
    """Insert a test API key whose hash matches TEST_API_KEY_RAW."""
    api_key = UserApiKey(
        id=100,
        user_id=seed_user.id,
        key_hash=TEST_API_KEY_HASH,
        key_prefix="sk-test-",
        name="integration-test-key",
        status=1,
        quota_mode=0,
        quota_limit=0,
        quota_used=0,
    )
    db_session.add(api_key)
    await db_session.flush()
    return api_key


@pytest_asyncio.fixture
async def seed_routing_config(db_session):
    """Insert minimal routing config so 'gpt-4o-mini' can be routed.

    Creates: ModelVendor -> ModelCatalog -> Pool -> PoolAccount -> PoolModelConfig.
    """
    # 1. ModelVendor
    vendor = ModelVendor(
        id=1000,
        slug="openai",
        name="OpenAI",
        is_active=True,
        sort_order=0,
    )
    db_session.add(vendor)
    await db_session.flush()

    # 2. ModelCatalog with pricing
    model = ModelCatalog(
        id=2000,
        slug="gpt-4o-mini",
        routing_slug="gpt-4o-mini",
        name="GPT-4o Mini",
        vendor_id=vendor.id,
        sale_input_per_million=150_000,   # 0.15 yuan per million tokens
        sale_output_per_million=600_000,  # 0.6 yuan per million tokens
        is_active=True,
        sort_order=0,
    )
    db_session.add(model)
    await db_session.flush()

    # 3. Pool
    pool = Pool(
        id=3000,
        slug="test-pool",
        name="Test Pool",
        base_url="https://api.openai.com/v1",
        is_enabled=True,
        priority=10,
        weight=1,
    )
    db_session.add(pool)
    await db_session.flush()

    # 4. PoolAccount with encrypted API key
    enc = encrypt_api_key("sk-fake-upstream-key-for-testing", MASTER_KEY_HEX)
    account = PoolAccount(
        id=4000,
        pool_id=pool.id,
        name="test-account",
        api_key_enc=enc,
        mask="sk-f****ting",
        balance=999_999_999,
        status=0,  # ACTIVE
        weight=1,
    )
    db_session.add(account)
    await db_session.flush()

    # 5. PoolModelConfig linking pool to model
    pmc = PoolModelConfig(
        id=5000,
        pool_id=pool.id,
        model_slug="gpt-4o-mini",
        upstream_model_id="gpt-4o-mini",
        cost_input_per_million=75_000,
        cost_output_per_million=300_000,
        is_enabled=True,
    )
    db_session.add(pmc)
    await db_session.flush()

    return {
        "vendor": vendor,
        "model": model,
        "pool": pool,
        "account": account,
        "pool_model_config": pmc,
    }


@pytest_asyncio.fixture
async def init_relay(db_session, session_factory, cache_redis, seed_routing_config):
    """Initialize relay globals with real components.

    Depends on seed_routing_config so routing data is available in DB.
    """
    from api_service.relay.channel_affinity import ChannelAffinityStore
    from api_service.relay.channel_selector import ChannelSelector
    from api_service.relay.config_cache import RoutingConfigCache
    from api_service.relay.dependencies import init_relay_globals, shutdown_relay
    from api_service.relay.inference_client import InferenceClient
    from api_service.relay.rate_limiter import RateLimiter
    from api_service.relay.sdk_clients import SdkClientPool

    # 1. RoutingConfigCache — start against session_factory + cache_redis
    config_cache = RoutingConfigCache(cache_redis)
    await config_cache.start(session_factory)

    # 2. InferenceClient
    inference_client = InferenceClient(
        base_url=os.environ["INFERENCE_SERVICE_URL"],
        secret=os.environ.get("INFERENCE_SERVICE_SECRET", ""),
    )

    # 3. ChannelSelector
    channel_selector = ChannelSelector(
        cooldown_seconds=30.0,
        auto_disable_enabled=False,
        auto_disable_threshold=5,
    )

    # 4. ChannelAffinityStore (disabled for tests)
    affinity_store = ChannelAffinityStore(redis=None, ttl=300)

    # 5. SdkClientPool
    sdk_client_pool = SdkClientPool(max_size=64)

    # 6. RateLimiter (disabled via env)
    rate_limiter = RateLimiter(
        redis=cache_redis,
        default_user_rpm=60,
        global_rpm=0,
    )

    init_relay_globals(
        config_cache=config_cache,
        inference_client=inference_client,
        channel_selector=channel_selector,
        affinity_store=affinity_store,
        sdk_client_pool=sdk_client_pool,
        rate_limiter=rate_limiter,
    )

    yield

    await shutdown_relay()


@pytest_asyncio.fixture
async def seed_balance_in_redis(cache_redis, seed_user):
    """Set user balance in Redis (hot path for billing)."""
    await cache_redis.set(f"user:quota:{seed_user.id}", str(seed_user.balance))
    return seed_user.balance

