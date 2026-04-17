"""Unit tests for router_service.utils.runtime_config."""

import json
import os
import tempfile

import pytest
from router_service.utils.runtime_config import (
    RuntimeConfigStore,
    normalize_runtime_config,
    build_default_runtime_config,
    clone_runtime_config,
)


class TestNormalizeRuntimeConfig:
    def test_default(self):
        config = normalize_runtime_config(build_default_runtime_config())
        assert config["router_alias"] == "auto"
        assert set(config["tier_model_map"].keys()) == {1, 2, 3, 4, 5}
        assert len(config["weights"]) == 5

    def test_valid_config(self):
        raw = {
            "router_alias": "test-router",
            "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
            "weights": {"纠错": 1.0, "工具调用": 2.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
            "score_bands": "0-5:3,5-10:1",
            "tier_model_map": {"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"},
            "model_providers": {
                "a": {"provider_slug": "p", "api_key": "k", "api_base": "http://x", "upstream_model": "m"},
            },
        }
        config = normalize_runtime_config(raw)
        assert config["weights"]["工具调用"] == 2.0
        assert config["router_alias"] == "test-router"

    def test_wrong_route_order_raises(self):
        raw = build_default_runtime_config()
        raw["route_order"] = ["a", "b", "c", "d", "e"]
        with pytest.raises(ValueError, match="route_order"):
            normalize_runtime_config(raw)

    def test_negative_weight_raises(self):
        raw = build_default_runtime_config()
        raw["weights"]["纠错"] = -1.0
        with pytest.raises(ValueError, match="non-negative"):
            normalize_runtime_config(raw)

    def test_missing_tier_raises(self):
        raw = build_default_runtime_config()
        raw["tier_model_map"] = {"1": "a", "2": "b"}
        with pytest.raises(ValueError, match="tiers 1..5"):
            normalize_runtime_config(raw)


class TestCloneRuntimeConfig:
    def test_clone_is_independent(self):
        config = normalize_runtime_config(build_default_runtime_config())
        cloned = clone_runtime_config(config)
        cloned["weights"]["纠错"] = 999.0
        assert config["weights"]["纠错"] != 999.0


class TestRuntimeConfigStore:
    def test_load_creates_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            store = RuntimeConfigStore(path)
            config = store.load()
            assert os.path.exists(path)
            assert config["router_alias"] == "auto"

    def test_hot_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            store = RuntimeConfigStore(path)
            config1 = store.load()

            # Modify file
            with open(path, "r") as f:
                raw = json.load(f)
            raw["router_alias"] = "changed-alias"
            with open(path, "w") as f:
                json.dump(raw, f)

            # Force mtime change
            import time
            time.sleep(0.05)
            os.utime(path, None)

            config2 = store.load()
            assert config2["router_alias"] == "changed-alias"

    def test_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            store = RuntimeConfigStore(path)
            config1 = store.load()
            config2 = store.load()
            assert config1 is config2  # same object = cache hit
