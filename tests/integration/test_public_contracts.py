from __future__ import annotations

import pytest


def test_service_package_roots_expose_only_final_public_contracts():
    from admin_service import UserStatsGateway, require_super_admin
    from user_service import require_active_user

    assert UserStatsGateway.__module__ == "admin_service.gateway"
    assert require_super_admin.__module__ == "admin_service.policies"
    assert require_active_user.__module__ == "user_service.policies"


def test_router_gateway_exposes_final_contracts_only():
    from router_service.gateway import UserIdentityGateway, ValidatedApiKey
    from router_service.schemas.requests import ChatCompletionRequest, CompletionRequest

    assert UserIdentityGateway.__module__ == "router_service.gateway"
    assert ValidatedApiKey.__module__ == "router_service.gateway"
    assert ChatCompletionRequest.__module__ == "router_service.schemas.requests"
    assert CompletionRequest.__module__ == "router_service.schemas.requests"


def test_router_schema_package_does_not_reexport_removed_request_symbols():
    import router_service.schemas as router_schemas

    assert not hasattr(router_schemas, "ChatCompletionRequest")
    assert not hasattr(router_schemas, "CompletionRequest")

    with pytest.raises(ImportError):
        exec("from router_service.schemas import ChatCompletionRequest")
