"""Unit tests for router_service.services.upstream."""

import pytest
from router_service.services.upstream import (
    normalize_api_base,
    resolve_model_provider_target,
    strip_think_tags,
)


class TestNormalizeApiBase:
    def test_strip_trailing_slash(self):
        assert normalize_api_base("https://api.example.com/v1/") == "https://api.example.com/v1"

    def test_strip_chat_completions(self):
        assert normalize_api_base("https://api.example.com/v1/chat/completions") == "https://api.example.com/v1"

    def test_strip_models(self):
        assert normalize_api_base("https://api.example.com/v1/models") == "https://api.example.com/v1"

    def test_empty(self):
        assert normalize_api_base("") == ""


class TestResolveModelProviderTarget:
    def test_valid(self):
        providers = {
            "gpt-5-4": {
                "provider_slug": "autodl",
                "api_key": "test-key",
                "api_base": "https://api.example.com/v1",
                "upstream_model": "gpt-5.4",
            }
        }
        target = resolve_model_provider_target("gpt-5-4", providers)
        assert target["logical_model"] == "gpt-5-4"
        assert target["upstream_model"] == "gpt-5.4"
        assert target["api_key"] == "test-key"

    def test_missing_model_raises(self):
        with pytest.raises(KeyError, match="missing provider"):
            resolve_model_provider_target("nonexistent", {})


class TestStripThinkTags:
    def test_basic(self):
        text = "<think>reasoning here</think>actual response"
        assert strip_think_tags(text) == "actual response"

    def test_no_tags(self):
        assert strip_think_tags("hello world") == "hello world"

    def test_multiline(self):
        text = "<think>\nline1\nline2\n</think>\nresult"
        assert strip_think_tags(text) == "result"

    def test_multiple_tags(self):
        text = "<think>a</think>middle<think>b</think>end"
        assert strip_think_tags(text) == "middleend"
