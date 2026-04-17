"""Unit tests for router_service.config."""

import json
import os
import tempfile

import pytest
from router_service.config import (
    FIVEWAY_ROUTE_ORDER,
    NORMALIZE_RANGES,
    ModelPathsConfig,
    load_model_paths,
)


class TestConstants:
    def test_route_order(self):
        assert len(FIVEWAY_ROUTE_ORDER) == 5
        assert FIVEWAY_ROUTE_ORDER[0] == "纠错"

    def test_normalize_ranges(self):
        for name in FIVEWAY_ROUTE_ORDER:
            assert name in NORMALIZE_RANGES
            lo, hi = NORMALIZE_RANGES[name]
            assert lo < hi


class TestModelPathsConfig:
    def test_load(self):
        config_data = {
            "qwen_backbone": "/tmp/test_model",
            "device": "cpu",
            "max_input_length": 2048,
            "routers": {
                "swe": {
                    "heads": [[1, 2], [3, 4]],
                    "model": "/tmp/swe.pth",
                    "scaler": "/tmp/swe.pkl",
                },
                "tool": {
                    "heads": [[5, 6]],
                    "model": "/tmp/tool.pth",
                    "scaler": "/tmp/tool.pkl",
                    "meta": "/tmp/tool_meta.json",
                },
            },
            "proto_artifact": "/tmp/proto.npz",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            path = f.name

        try:
            cfg = ModelPathsConfig(path)
            assert cfg.qwen_backbone == "/tmp/test_model"
            assert cfg.device == "cpu"
            assert cfg.max_input_length == 2048
            assert cfg.get_heads("swe") == [(1, 2), (3, 4)]
            assert cfg.get_model_path("tool") == "/tmp/tool.pth"
            assert cfg.get_meta_path("tool") == "/tmp/tool_meta.json"
            assert cfg.get_meta_path("swe") is None
        finally:
            os.unlink(path)
