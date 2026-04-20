"""Smoke tests for platform-level common helpers."""

import os
import sys

import pytest

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


class TestExceptions:
    def test_exception_base(self):
        from common.core.exceptions import APIException

        exc = APIException(status_code=400, detail="test error")
        assert exc.detail == "test error"
        assert exc.status_code == 400

    def test_auth_exception(self):
        from common.core.exceptions import AuthenticationException

        exc = AuthenticationException(detail="test error")
        assert exc.detail == "test error"

    def test_invalid_credentials(self):
        from common.core.exceptions import InvalidCredentialsException

        exc = InvalidCredentialsException()
        assert exc.detail is not None

    def test_token_exceptions(self):
        from common.core.exceptions import InvalidTokenException, TokenExpiredException

        assert InvalidTokenException().detail is not None
        assert TokenExpiredException().detail is not None


class TestTimezoneUtils:
    def test_now(self):
        from common.utils.timezone import now

        assert now() is not None

    def test_now_with_tz(self):
        from common.utils.timezone import now_with_tz

        value = now_with_tz()
        assert value is not None
        assert value.tzinfo is not None

    def test_format_iso(self):
        from datetime import datetime
        from common.utils.timezone import format_iso

        assert "2024" in format_iso(datetime(2024, 1, 1, 12, 0, 0))


class TestSnowflakeUtils:
    def test_generate_snowflake_id(self):
        from common.utils.snowflake import configure_snowflake, generate_snowflake_id

        configure_snowflake(worker_id=1, datacenter_id=1)
        ids = [generate_snowflake_id() for _ in range(10)]
        assert len(set(ids)) == 10

    def test_snowflake_id_type(self):
        from common.utils.snowflake import configure_snowflake, generate_snowflake_id

        configure_snowflake(worker_id=1, datacenter_id=1)
        uid = generate_snowflake_id()
        assert isinstance(uid, int)
        assert uid > 0


class TestPasswordUtils:
    def test_hash_and_verify(self):
        from common.utils.password import hash_password, verify_password

        password = "TestPassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_hash_consistency(self):
        from common.utils.password import hash_password, verify_password

        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestJWTUtils:
    def test_create_access_token(self):
        from common.utils.jwt import create_access_token, decode_token

        token = create_access_token(
            data={"uid": 12345, "sub": "12345"},
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
            expire_minutes=15,
        )
        payload = decode_token(
            token=token,
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
        )
        assert payload is not None
        assert payload["uid"] == 12345
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        from common.utils.jwt import create_refresh_token, decode_token

        token = create_refresh_token(
            data={"uid": 12345},
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
            expire_days=7,
        )
        payload = decode_token(
            token=token,
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
        )
        assert payload is not None
        assert payload["type"] == "refresh"

    def test_decode_invalid_token(self):
        from common.utils.jwt import decode_token

        assert decode_token(
            token="invalid_token",
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
        ) is None

    def test_get_token_jti(self):
        from common.utils.jwt import create_access_token, get_token_jti

        token = create_access_token(
            data={"uid": 12345},
            secret_key="test_secret_key_for_jwt_32bytes!",
            expire_minutes=15,
        )
        jti = get_token_jti(token)
        assert isinstance(jti, str)
        assert len(jti) == 64


class TestDatabase:
    def test_database_platform_imports(self):
        from common.db import ServiceDatabaseRuntime, SnowflakeIdMixin, TimestampMixin

        assert ServiceDatabaseRuntime is not None
        assert SnowflakeIdMixin is not None
        assert TimestampMixin is not None


class TestDatabaseRefactorPrimitives:
    def test_database_refactor_platform_imports(self):
        from common.db.base import SoftDeleteMixin
        from common.db.query import ListParams, PaginatedResult
        from common.db.repository import BaseRepository
        from common.gateway.base import BaseGateway

        assert SoftDeleteMixin is not None
        assert BaseRepository is not None
        assert ListParams is not None
        assert PaginatedResult is not None
        assert BaseGateway is not None

    def test_soft_delete_mixin_exposes_deleted_at_column(self):
        from common.db.base import SoftDeleteMixin

        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert SoftDeleteMixin.deleted_at.nullable is True

    def test_list_params_default_values(self):
        from common.db.query import ListParams

        params = ListParams()

        assert params.page == 1
        assert params.page_size > 0
        assert params.order_dir == "desc"

    def test_paginated_result_preserves_payload(self):
        from common.db.query import PaginatedResult

        payload = PaginatedResult(items=[1, 2], total=2, page=1, page_size=20)

        assert payload.items == [1, 2]
        assert payload.total == 2
        assert payload.page == 1
        assert payload.page_size == 20

    def test_base_gateway_can_store_service_name(self):
        from common.gateway.base import BaseGateway

        gateway = BaseGateway(service_name="admin-service")

        assert gateway.service_name == "admin-service"


class TestDatabaseRefactorPrimitives:
    def test_database_refactor_platform_imports(self):
        from common.db.base import SoftDeleteMixin
        from common.db.query import ListParams, PaginatedResult
        from common.db.repository import BaseRepository
        from common.gateway.base import BaseGateway

        assert SoftDeleteMixin is not None
        assert BaseRepository is not None
        assert ListParams is not None
        assert PaginatedResult is not None
        assert BaseGateway is not None

    def test_soft_delete_mixin_exposes_deleted_at_column(self):
        from common.db.base import SoftDeleteMixin

        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert SoftDeleteMixin.deleted_at.nullable is True

    def test_list_params_default_values(self):
        from common.db.query import ListParams

        params = ListParams()

        assert params.page == 1
        assert params.page_size > 0
        assert params.order_dir == "desc"

    def test_paginated_result_preserves_payload(self):
        from common.db.query import PaginatedResult

        payload = PaginatedResult(items=[1, 2], total=2, page=1, page_size=20)

        assert payload.items == [1, 2]
        assert payload.total == 2
        assert payload.page == 1
        assert payload.page_size == 20

    def test_base_gateway_can_store_service_name(self):
        from common.gateway.base import BaseGateway

        gateway = BaseGateway(service_name="admin-service")

        assert gateway.service_name == "admin-service"

    def test_database_refactor_platform_imports(self):
        from common.db.base import SoftDeleteMixin
        from common.db.query import ListParams, PaginatedResult
        from common.db.repository import BaseRepository
        from common.gateway.base import BaseGateway

        assert SoftDeleteMixin is not None
        assert BaseRepository is not None
        assert ListParams is not None
        assert PaginatedResult is not None
        assert BaseGateway is not None

    def test_soft_delete_mixin_exposes_deleted_at_column(self):
        from common.db.base import SoftDeleteMixin

        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert SoftDeleteMixin.deleted_at.nullable is True

    def test_list_params_default_values(self):
        from common.db.query import ListParams

        params = ListParams()

        assert params.page == 1
        assert params.page_size > 0
        assert params.order_dir == "desc"

    def test_paginated_result_preserves_payload(self):
        from common.db.query import PaginatedResult

        payload = PaginatedResult(items=[1, 2], total=2, page=1, page_size=20)

        assert payload.items == [1, 2]
        assert payload.total == 2
        assert payload.page == 1
        assert payload.page_size == 20

    def test_base_gateway_can_store_service_name(self):
        from common.gateway.base import BaseGateway

        gateway = BaseGateway(service_name="admin-service")

        assert gateway.service_name == "admin-service"

    def test_database_refactor_platform_imports(self):
        from common.db.base import SoftDeleteMixin
        from common.db.query import ListParams, PaginatedResult
        from common.db.repository import BaseRepository
        from common.gateway.base import BaseGateway

        assert SoftDeleteMixin is not None
        assert BaseRepository is not None
        assert ListParams is not None
        assert PaginatedResult is not None
        assert BaseGateway is not None

    def test_soft_delete_mixin_exposes_deleted_at_column(self):
        from common.db.base import SoftDeleteMixin

        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert SoftDeleteMixin.deleted_at.nullable is True

    def test_list_params_default_values(self):
        from common.db.query import ListParams

        params = ListParams()

        assert params.page == 1
        assert params.page_size > 0
        assert params.order_dir == "desc"

    def test_paginated_result_preserves_payload(self):
        from common.db.query import PaginatedResult

        payload = PaginatedResult(items=[1, 2], total=2, page=1, page_size=20)

        assert payload.items == [1, 2]
        assert payload.total == 2
        assert payload.page == 1
        assert payload.page_size == 20

    def test_base_gateway_can_store_service_name(self):
        from common.gateway.base import BaseGateway

        gateway = BaseGateway(service_name="admin-service")

        assert gateway.service_name == "admin-service"


class TestObservabilityAndHealth:
    def test_phase4_platform_imports(self):
        from common.health import build_readiness_response, check_database_ready
        from common.observability import (
            REQUEST_ID_HEADER,
            configure_logging,
            get_request_id,
            install_observability,
            log_event,
            reset_request_id,
            set_request_id,
        )
        from common.internal import (
            InternalCircuitOpenError,
            InternalServiceUnavailableError,
            reset_internal_circuit_breakers,
        )

        assert REQUEST_ID_HEADER == "X-Request-ID"
        assert configure_logging is not None
        assert install_observability is not None
        assert log_event is not None
        assert set_request_id is not None
        assert get_request_id is not None
        assert reset_request_id is not None
        assert InternalServiceUnavailableError is not None
        assert InternalCircuitOpenError is not None
        assert reset_internal_circuit_breakers is not None
        assert check_database_ready is not None
        assert build_readiness_response is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
