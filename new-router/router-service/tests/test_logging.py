"""Unit tests for router_service.logging."""

import json
import logging
import os
import tempfile

from router_service.logging import (
    setup_logging,
    get_app_logger,
    get_routing_logger,
    get_upstream_logger,
    log_routing_decision,
    log_upstream_call,
    JsonLineFormatter,
    _initialized,
)


class TestJsonLineFormatter:
    def test_dict_message(self):
        formatter = JsonLineFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg={"request_id": "abc", "score": 1.5},
            args=None, exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["request_id"] == "abc"
        assert parsed["score"] == 1.5
        assert "ts" in parsed

    def test_string_message(self):
        formatter = JsonLineFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello world",
            args=None, exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["message"] == "hello world"


class TestSetupLogging:
    def test_creates_log_dir(self):
        import router_service.logging as log_mod
        # Reset for test
        log_mod._initialized = False
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "test_logs")
            setup_logging(log_dir=log_dir)
            assert os.path.isdir(log_dir)
        # Reset again
        log_mod._initialized = False

    def test_loggers_exist(self):
        import router_service.logging as log_mod
        log_mod._initialized = False
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir)
            assert get_app_logger().name == "router_service"
            assert get_routing_logger().name == "router_service.routing"
            assert get_upstream_logger().name == "router_service.upstream"
        log_mod._initialized = False
