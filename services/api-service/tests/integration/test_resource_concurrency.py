"""Resource constraint validation and Snowflake ID concurrency tests.

Validates:
- D-09: 4-worker uvicorn stays under 1.5GB total RSS
- D-10: Memory test marked @pytest.mark.slow
- D-11: Snowflake IDs from worker_id=1 and worker_id=2 have zero collisions
- D-12: Cross-worker IDs never collide
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import psutil
import pytest

from api_service.common.utils.snowflake import (
    SnowflakeIDGenerator,
    configure_snowflake,
    generate_snowflake_id,
    get_snowflake_generator,
)

# ══════════════════════════════════════════════════════════════════════════════
# Part A: Memory limit test (D-09, D-10)
# ══════════════════════════════════════════════════════════════════════════════

API_SERVICE_DIR = Path(__file__).resolve().parents[2]  # services/api-service


@pytest.fixture
def _reset_snowflake():
    """Clear snowflake generator cache between tests."""
    get_snowflake_generator.cache_clear()
    yield
    get_snowflake_generator.cache_clear()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_four_workers_memory_under_limit():
    """4-worker uvicorn total RSS must stay under 1.5GB (2h4g deployment constraint).

    Spawns a real uvicorn process with 4 workers, warms up with concurrent
    requests, then measures total RSS of parent + all children.
    """
    env = {
        **os.environ,
        "DATABASE_URL": "mysql+aiomysql://root:abc123@localhost:3306/eucal_ai_test",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "CACHE_REDIS_URL": "redis://127.0.0.1:6379/2",
        "WORKER_QUEUE_REDIS_URL": "redis://127.0.0.1:6379/1",
        "JWT_SECRET_KEY": "test-jwt-secret-key-at-least-32-characters-long",
        "INTERNAL_SECRET": "test-internal-secret-at-least-32-characters-long",
        "INFERENCE_SERVICE_URL": "http://127.0.0.1:8004",
        "INFERENCE_SERVICE_SECRET": "test-inference-secret-at-least-32-chars",
        "PROVIDER_SECRET_MASTER_KEY": "a" * 64,
        "BOOTSTRAP_SUPERADMIN_ENABLED": "false",
        "BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP": "false",
        "RATE_LIMIT_ENABLED": "false",
    }

    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api_service.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "9999",
                "--workers",
                "4",
            ],
            env=env,
            cwd=str(API_SERVICE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for startup: poll /health every 1s, timeout 30s
        base_url = "http://127.0.0.1:9999"
        started = False
        deadline = time.time() + 30
        async with httpx.AsyncClient(timeout=5.0) as client:
            while time.time() < deadline:
                try:
                    resp = await client.get(f"{base_url}/health")
                    if resp.status_code == 200:
                        started = True
                        break
                except (httpx.ConnectError, httpx.ReadError):
                    pass
                await asyncio.sleep(1.0)

        assert started, "uvicorn with 4 workers failed to start within 30s"

        # Warm up workers with 20 concurrent requests to /health
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            tasks = [client.get("/health") for _ in range(20)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            # At least some should succeed
            successes = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
            assert len(successes) >= 10, f"Only {len(successes)}/20 warmup requests succeeded"

        # Measure memory: parent + all children
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        total_rss = parent.memory_info().rss + sum(
            c.memory_info().rss for c in children
        )

        # Assert under 1.5GB
        limit_bytes = 1.5 * 1024**3
        print(f"\nTotal RSS: {total_rss / 1024**2:.1f} MB")
        print(f"Limit: {limit_bytes / 1024**2:.1f} MB")
        print(f"Workers found: {len(children)}")
        assert total_rss < limit_bytes, (
            f"Total RSS {total_rss / 1024**2:.1f} MB exceeds 1.5GB limit"
        )

    finally:
        # Ensure process cleanup (T-09-06 mitigation)
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


# ══════════════════════════════════════════════════════════════════════════════
# Part B: Snowflake ID concurrency tests (D-11, D-12)
# ══════════════════════════════════════════════════════════════════════════════


def _generate_ids_with_own_generator(
    worker_id: int, datacenter_id: int, count: int
) -> list[int]:
    """Generate IDs with a dedicated generator (simulates separate process).

    Each uvicorn worker process has its own generator with a unique instance_id.
    """
    gen = SnowflakeIDGenerator(worker_id=worker_id, datacenter_id=datacenter_id)
    return gen.generate_batch(count)


@pytest.mark.asyncio
async def test_snowflake_worker1_no_collision(_reset_snowflake):
    """4 coroutines x 10000 IDs with worker_id=1 must produce 40000 unique IDs.

    Simulates the production pattern: single-threaded asyncio event loop with
    multiple concurrent coroutines calling generate_snowflake_id(). In production,
    each uvicorn worker is a separate process running one event loop — concurrent
    requests are coroutines, not threads.
    """
    configure_snowflake(worker_id=1, datacenter_id=1)
    ids_per_coroutine = 10_000
    num_coroutines = 4

    async def _generate_batch(n: int) -> list[int]:
        """Generate IDs in a coroutine (yields control between batches)."""
        ids = []
        for i in range(n):
            ids.append(generate_snowflake_id())
            # Yield control every 1000 IDs to simulate real async interleaving
            if i % 1000 == 999:
                await asyncio.sleep(0)
        return ids

    tasks = [_generate_batch(ids_per_coroutine) for _ in range(num_coroutines)]
    results = await asyncio.gather(*tasks)

    all_ids: list[int] = []
    for batch in results:
        all_ids.extend(batch)

    assert len(all_ids) == 40_000
    id_set = set(all_ids)
    assert len(id_set) == 40_000, (
        f"Collision detected: {40_000 - len(id_set)} duplicate IDs from worker_id=1"
    )


@pytest.mark.asyncio
async def test_snowflake_worker2_no_collision(_reset_snowflake):
    """4 coroutines x 10000 IDs with worker_id=2 must produce 40000 unique IDs.

    Same as worker1 test but with worker_id=2 configuration.
    """
    configure_snowflake(worker_id=2, datacenter_id=1)
    ids_per_coroutine = 10_000
    num_coroutines = 4

    async def _generate_batch(n: int) -> list[int]:
        """Generate IDs in a coroutine (yields control between batches)."""
        ids = []
        for i in range(n):
            ids.append(generate_snowflake_id())
            if i % 1000 == 999:
                await asyncio.sleep(0)
        return ids

    tasks = [_generate_batch(ids_per_coroutine) for _ in range(num_coroutines)]
    results = await asyncio.gather(*tasks)

    all_ids: list[int] = []
    for batch in results:
        all_ids.extend(batch)

    assert len(all_ids) == 40_000
    id_set = set(all_ids)
    assert len(id_set) == 40_000, (
        f"Collision detected: {40_000 - len(id_set)} duplicate IDs from worker_id=2"
    )


@pytest.mark.asyncio
async def test_snowflake_cross_worker_no_collision(_reset_snowflake):
    """IDs from worker_id=1 and worker_id=2 must never overlap (D-12).

    Generates 10000 IDs from each worker configuration and verifies
    the combined set has zero duplicates. Each worker has its own
    generator instance (simulating separate processes).
    """
    datacenter_id = 1
    count = 10_000

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_w1 = loop.run_in_executor(
            executor, _generate_ids_with_own_generator, 1, datacenter_id, count
        )
        future_w2 = loop.run_in_executor(
            executor, _generate_ids_with_own_generator, 2, datacenter_id, count
        )
        ids_w1, ids_w2 = await asyncio.gather(future_w1, future_w2)

    combined = set(ids_w1) | set(ids_w2)
    total_expected = count * 2

    # First verify each set is internally unique
    assert len(set(ids_w1)) == count, "worker_id=1 has internal collisions"
    assert len(set(ids_w2)) == count, "worker_id=2 has internal collisions"

    # Then verify no cross-worker collision
    assert len(combined) == total_expected, (
        f"Cross-worker collision: {total_expected - len(combined)} overlapping IDs "
        f"between worker_id=1 and worker_id=2"
    )
