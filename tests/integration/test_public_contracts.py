from __future__ import annotations


def test_service_package_roots_expose_only_final_public_contracts():
    from admin_service import UserStatsGateway, require_super_admin
    from user_service import AdminInvitationGateway, require_active_user

    assert UserStatsGateway.__module__ == "admin_service.gateway"
    assert require_super_admin.__module__ == "admin_service.policies"
    assert AdminInvitationGateway.__module__ == "user_service.gateway"
    assert require_active_user.__module__ == "user_service.policies"


def test_router_and_testing_gateways_expose_final_contracts_only():
    import testing_service.gateway as testing_gateway
    from router_service.gateway import UserIdentityGateway, ValidatedApiKey
    from testing_service.gateway import AdminIdentityGateway

    assert UserIdentityGateway.__module__ == "router_service.gateway"
    assert ValidatedApiKey.__module__ == "router_service.gateway"
    assert AdminIdentityGateway.__module__ == "testing_service.gateway"
    assert not hasattr(testing_gateway, "AdminIdentityClientService")
