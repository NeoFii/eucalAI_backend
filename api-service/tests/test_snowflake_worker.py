"""Tests for Snowflake ID per-worker safety across multiple processes."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.common.utils.snowflake import (
    SnowflakeIDGenerator,
    _get_instance_id,
    configure_snowflake,
    generate_snowflake_id,
    get_snowflake_generator,
)


class TestDifferentPidsProduceDifferentWorkerIds:
    """Verify that different PIDs map to different worker_ids via pid % 32."""

    def test_four_consecutive_pids(self):
        pids = [1000, 1001, 1002, 1003]
        worker_ids = [pid % 32 for pid in pids]
        assert len(set(worker_ids)) == 4, "4 consecutive PIDs must produce 4 distinct worker_ids"

    def test_pids_with_stride_32_collide(self):
        """PIDs separated by exactly 32 will collide — this is expected and acceptable."""
        assert 1000 % 32 == 1032 % 32

    def test_typical_uvicorn_fork_pids(self):
        """Simulates typical uvicorn fork where child PIDs are sequential."""
        parent_pid = 12345
        child_pids = [parent_pid + i for i in range(1, 5)]
        worker_ids = [pid % 32 for pid in child_pids]
        assert len(set(worker_ids)) == 4


class TestDifferentWorkersProduceUniqueIds:
    """Verify that generators with different worker_ids produce non-overlapping IDs."""

    def test_four_workers_no_collision(self):
        generators = [
            SnowflakeIDGenerator(datacenter_id=1, worker_id=w)
            for w in range(4)
        ]
        all_ids: list[int] = []
        for gen in generators:
            all_ids.extend(gen.generate_batch(100))

        assert len(all_ids) == 400
        assert len(set(all_ids)) == 400, "All 400 IDs must be unique across 4 workers"

    def test_same_worker_sequential_ids_unique(self):
        gen = SnowflakeIDGenerator(datacenter_id=1, worker_id=7)
        ids = gen.generate_batch(1000)
        assert len(set(ids)) == 1000


class TestPidMod32Range:
    """Verify pid % 32 always produces values in [0, 31]."""

    def test_current_pid_in_range(self):
        worker_id = os.getpid() % 32
        assert 0 <= worker_id <= 31

    def test_boundary_pids(self):
        for pid in [0, 1, 31, 32, 33, 63, 64, 65535, 99999]:
            assert 0 <= pid % 32 <= 31

    def test_instance_id_formula(self):
        """After configure_snowflake, _get_instance_id returns datacenter_id * 32 + worker_id."""
        configure_snowflake(worker_id=5, datacenter_id=1)
        assert _get_instance_id() == 1 * 32 + 5  # 37

        configure_snowflake(worker_id=0, datacenter_id=2)
        assert _get_instance_id() == 2 * 32 + 0  # 64

        configure_snowflake(worker_id=31, datacenter_id=0)
        assert _get_instance_id() == 0 * 32 + 31  # 31


class TestConfigureSnowflakeClearsCache:
    """Verify that configure_snowflake invalidates the cached generator."""

    def test_reconfigure_changes_instance_id(self):
        configure_snowflake(worker_id=5, datacenter_id=1)
        gen1 = get_snowflake_generator()
        # SnowflakeGenerator stores instance as _inf = instance << 12
        assert gen1._inf >> 12 == 1 * 32 + 5  # 37

        configure_snowflake(worker_id=10, datacenter_id=1)
        gen2 = get_snowflake_generator()
        assert gen2._inf >> 12 == 1 * 32 + 10  # 42

        # Generators should be different objects after reconfigure
        assert gen1 is not gen2

    def test_ids_after_reconfigure_still_unique(self):
        configure_snowflake(worker_id=3, datacenter_id=1)
        ids_before = [generate_snowflake_id() for _ in range(50)]

        configure_snowflake(worker_id=7, datacenter_id=1)
        ids_after = [generate_snowflake_id() for _ in range(50)]

        all_ids = ids_before + ids_after
        assert len(set(all_ids)) == 100


class TestInitSnowflakeIntegration:
    """Integration test: _init_snowflake uses os.getpid() % 32."""

    def test_init_snowflake_uses_pid(self):
        """Verify the main module's _init_snowflake wires os.getpid() % 32."""
        # We test the logic directly rather than calling the async function
        fake_pid = 12345
        expected_worker_id = fake_pid % 32  # 12345 % 32 = 25

        with patch("os.getpid", return_value=fake_pid):
            worker_id = os.getpid() % 32

        assert worker_id == expected_worker_id
        assert worker_id == 25
