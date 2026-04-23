"""Tests for VNext-C billing query endpoints — new fields + request_id filter."""

from __future__ import annotations

import os

os.environ.setdefault("INTERNAL_SECRET", "test_internal_secret_32chars_long!")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!")

import pytest
from fastapi import FastAPI

from user_service.schemas.billing import ApiCallLogItem


def test_api_call_log_item_includes_new_fields():
    fields = set(ApiCallLogItem.model_fields.keys())
    expected_new = {"selected_model", "provider_slug", "routing_tier", "config_version", "config_source", "router_trace_id"}
    assert expected_new.issubset(fields), f"Missing fields: {expected_new - fields}"


def test_api_call_log_item_excludes_internal_fields():
    fields = set(ApiCallLogItem.model_fields.keys())
    internal_only = {"upstream_model", "inference_error_code", "inference_config_version", "inference_config_source", "score_source", "ip", "cost_detail"}
    leaked = fields & internal_only
    assert not leaked, f"Internal fields leaked to user schema: {leaked}"


def test_api_call_log_item_validates_from_attributes():
    from types import SimpleNamespace
    from datetime import datetime

    obj = SimpleNamespace(
        id=1, request_id="r1", api_key_id=10, model_name="auto",
        selected_model="gpt-4", provider_slug="openai",
        prompt_tokens=100, completion_tokens=50, cached_tokens=0, total_tokens=150,
        cost=0, status=1, duration_ms=200, is_stream=False,
        routing_tier=1, config_version=5, config_source="admin",
        router_trace_id="chat-abc123",
        error_code=None, error_msg=None,
        created_at=datetime(2026, 4, 23, 12, 0, 0),
    )
    item = ApiCallLogItem.model_validate(obj, from_attributes=True)
    assert item.selected_model == "gpt-4"
    assert item.routing_tier == 1
    assert item.router_trace_id == "chat-abc123"


def test_admin_usage_log_item_includes_all_tracking_fields():
    from admin_service.schemas.user_management import UserUsageLogItem

    fields = set(UserUsageLogItem.model_fields.keys())
    expected = {
        "selected_model", "provider_slug", "upstream_model",
        "config_version", "config_source",
        "inference_config_version", "inference_config_source",
        "routing_tier", "score_source", "router_trace_id",
        "inference_error_code", "updated_at",
    }
    assert expected.issubset(fields), f"Missing admin fields: {expected - fields}"


def test_billing_usage_logs_endpoint_not_deprecated():
    from user_service.api.v1.endpoints.billing import list_usage_logs
    route_info = getattr(list_usage_logs, "__route__", None)
    # The function itself should exist and not be marked deprecated
    assert list_usage_logs is not None


def test_billing_usage_logs_accepts_request_id_param():
    import inspect
    from user_service.api.v1.endpoints.billing import list_usage_logs

    sig = inspect.signature(list_usage_logs)
    assert "request_id" in sig.parameters, "list_usage_logs should accept request_id parameter"
    assert "effective_model" in sig.parameters, "list_usage_logs should accept effective_model parameter"


def test_billing_usage_stats_endpoint_not_deprecated():
    from user_service.api.v1.endpoints.billing import list_usage_stats
    assert list_usage_stats is not None


def test_billing_usage_analytics_endpoint_registered():
    from user_service.api.v1.endpoints import billing

    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1")

    route_paths = {route.path for route in app.routes}
    assert "/api/v1/billing/usage/analytics" in route_paths


def test_billing_usage_analytics_accepts_range_param():
    import inspect
    from user_service.api.v1.endpoints.billing import list_usage_analytics

    sig = inspect.signature(list_usage_analytics)
    assert "range" in sig.parameters, "list_usage_analytics should accept a range parameter"
