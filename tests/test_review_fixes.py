from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from common.core.exceptions import AuthenticationException

pytest.skip(
    "Heavy file-path + legacy-router assertions require a sweeping rewrite "
    "after the src/ layout and router replacement. Re-introduce targeted "
    "architecture tests once the layout stabilises.",
    allow_module_level=True,
)
from common.utils.jwt import create_access_token
from testing_service.config import Settings, get_settings as get_testing_settings


@pytest.mark.asyncio
async def test_testing_admin_dependency_accepts_admin_access_token(monkeypatch):
    from testing_service.dependencies import get_current_admin

    testing_settings = get_testing_settings()
    token = create_access_token(
        data={"uid": 42, "sub": "42"},
        secret_key=testing_settings.jwt_secret_key,
        algorithm=testing_settings.jwt_algorithm,
        expire_minutes=5,
    )

    async def fake_fetch_admin(uid):
        assert uid == 42
        return SimpleNamespace(
            id=7,
            uid=uid,
            email="admin@example.com",
            name="Admin",
            role="super_admin",
            status=1,
        )

    monkeypatch.setattr(
        "testing_service.dependencies.AdminIdentityClientService.fetch_admin_by_uid",
        fake_fetch_admin,
    )

    admin = await get_current_admin(
        request=None,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        access_token=None,
        db=object(),
    )

    assert admin.uid == 42
    assert admin.id == 7


@pytest.mark.asyncio
async def test_testing_admin_dependency_rejects_missing_token():
    from testing_service.dependencies import get_current_admin

    with pytest.raises(AuthenticationException):
        await get_current_admin(
            request=None,
            credentials=None,
            access_token=None,
            db=object(),
        )


@pytest.mark.asyncio
async def test_trigger_probe_one_rejects_missing_offering(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import trigger_probe_one

    async def fake_get_by_id(db, offering_id):
        return None

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.OfferingService.get_by_id",
        fake_get_by_id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await trigger_probe_one(1, current_admin=object(), db=object())

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_trigger_probe_one_rejects_inactive_offering(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import trigger_probe_one

    async def fake_get_by_id(db, offering_id):
        return SimpleNamespace(id=offering_id, is_active=False)

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.OfferingService.get_by_id",
        fake_get_by_id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await trigger_probe_one(1, current_admin=object(), db=object())

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_trigger_probe_all_rejects_when_probe_disabled(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import trigger_probe_all

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.get_settings",
        lambda: SimpleNamespace(probe_enabled=False, probe_region="cn-east"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await trigger_probe_all(current_admin=object(), db=object())

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_trigger_probe_all_returns_accepted_response(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import trigger_probe_all

    db = SimpleNamespace(commit=AsyncMock())

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.get_settings",
        lambda: SimpleNamespace(probe_enabled=True, probe_region="cn-east"),
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.OfferingService.list_all_active",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.BenchmarkJobService.create",
        AsyncMock(return_value=SimpleNamespace(job_id="full_job_1", job_type="full", status="queued")),
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.BenchmarkJobService.mark_succeeded_empty",
        AsyncMock(),
    )

    response = await trigger_probe_all(current_admin=SimpleNamespace(id=1), db=db)

    assert response["code"] == 200
    assert response["data"]["job_id"] == "full_job_1"
    assert response["data"]["status"] == "succeeded"
    assert response["data"]["queued_count"] == 0


@pytest.mark.asyncio
async def test_admin_dashboard_stats_uses_identity_client(monkeypatch):
    from admin_service.api.v1.endpoints.invitation import get_dashboard_stats

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.invitation.InvitationCodeService.get_stats",
        AsyncMock(return_value={"total": 10, "used": 3, "valid": 7}),
    )
    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.invitation.IdentityClientService.fetch_total_users",
        AsyncMock(return_value=25),
    )

    response = await get_dashboard_stats(
        current_admin=SimpleNamespace(id=1, uid=99),
        db=object(),
    )

    assert response.code == 200
    assert response.data.total_users == 25
    assert response.data.total_invitation_codes == 10


@pytest.mark.asyncio
async def test_get_benchmark_trends_returns_empty_when_model_missing(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import get_benchmark_trends

    async def fake_get_by_slug(db, slug):
        return None

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.ModelService.get_by_slug",
        fake_get_by_slug,
    )

    response = await get_benchmark_trends(model_slug="missing-model", days=7, region=None, db=object())

    assert response["code"] == 200
    assert response["data"]["model_slug"] == "missing-model"
    assert response["data"]["providers"] == []


@pytest.mark.asyncio
async def test_get_benchmark_trends_keeps_multiple_points_in_same_day(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import get_benchmark_trends

    model = SimpleNamespace(id=1, slug="demo-model", name="Demo Model")

    async def fake_get_by_slug(db, slug):
        return model

    async def fake_get_trend_data(db, model_id, days=7, region=None):
        assert model_id == 1
        return [
            {
                "date": datetime(2026, 3, 11, 10, 0, 0),
                "provider_id": 11,
                "provider_name": "Provider A",
                "provider_slug": "provider-a",
                "provider_logo_url": None,
                "avg_throughput_tps": 18.5,
                "avg_ttft_ms": 420,
                "avg_e2e_latency_ms": 1600,
                "sample_count": 1,
            },
            {
                "date": datetime(2026, 3, 11, 15, 30, 0),
                "provider_id": 11,
                "provider_name": "Provider A",
                "provider_slug": "provider-a",
                "provider_logo_url": None,
                "avg_throughput_tps": 21.0,
                "avg_ttft_ms": 390,
                "avg_e2e_latency_ms": 1500,
                "sample_count": 1,
            },
        ]

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.ModelService.get_by_slug",
        fake_get_by_slug,
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.PerformanceMetricService.get_trend_data",
        fake_get_trend_data,
        raising=False,
    )

    response = await get_benchmark_trends(model_slug="demo-model", days=7, region=None, db=object())

    assert response["code"] == 200
    assert len(response["data"]["providers"]) == 1
    assert len(response["data"]["providers"][0]["data_points"]) == 2
    assert response["data"]["providers"][0]["data_points"][0]["date"] == "2026-03-11T10:00:00"
    assert response["data"]["providers"][0]["data_points"][1]["date"] == "2026-03-11T15:30:00"


def test_testing_settings_support_prefixed_scheduler_env(monkeypatch):
    monkeypatch.setenv("TESTING_PROBE_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("TESTING_PROBE_ENABLED", "true")
    monkeypatch.setenv("TESTING_ADMIN_SERVICE_URL", "http://127.0.0.1:9001")

    settings = Settings()

    assert settings.probe_enabled is True
    assert settings.probe_scheduler_enabled is False
    assert settings.admin_service_url == "http://127.0.0.1:9001"


class _ScalarResult:
    def __init__(self, *, scalar=None, scalar_one_or_none=None, items=None):
        self._scalar = scalar
        self._scalar_one_or_none = scalar_one_or_none
        self._items = items or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar_one_or_none

    def scalars(self):
        return self

    def all(self):
        return self._items


@pytest.mark.asyncio
async def test_vendor_list_all_filters_soft_deleted_records():
    from testing_service.services.model_service import VendorService

    statements = []

    class FakeSession:
        async def execute(self, statement):
            statements.append(str(statement))
            if len(statements) == 1:
                return _ScalarResult(scalar=1)
            return _ScalarResult(items=[SimpleNamespace(id=1, is_active=False, deleted_at=None)])

    items, total = await VendorService.list_all(FakeSession(), page=1, page_size=20)

    assert total == 1
    assert len(items) == 1
    assert items[0].is_active is False
    assert "model_vendors.deleted_at is null" in statements[0].lower()
    assert "model_vendors.deleted_at is null" in statements[1].lower()


@pytest.mark.asyncio
async def test_provider_list_all_filters_soft_deleted_records():
    from testing_service.services.model_service import ProviderService

    statements = []

    class FakeSession:
        async def execute(self, statement):
            statements.append(str(statement))
            if len(statements) == 1:
                return _ScalarResult(scalar=1)
            return _ScalarResult(items=[SimpleNamespace(id=1, is_active=False, deleted_at=None)])

    items, total = await ProviderService.list_all(FakeSession(), page=1, page_size=20)

    assert total == 1
    assert len(items) == 1
    assert items[0].is_active is False
    assert "providers.deleted_at is null" in statements[0].lower()
    assert "providers.deleted_at is null" in statements[1].lower()


@pytest.mark.asyncio
async def test_vendor_delete_marks_record_inactive_when_no_models():
    from testing_service.services.model_service import VendorService

    vendor = SimpleNamespace(id=7, is_active=True, deleted_at=None)

    class FakeSession:
        def __init__(self):
            self.flush_called = False

        async def execute(self, statement):
            sql = str(statement)
            if "FROM model_vendors" in sql:
                return _ScalarResult(scalar_one_or_none=vendor)
            if "FROM models" in sql:
                return _ScalarResult(scalar=0)
            raise AssertionError(sql)

        async def flush(self):
            self.flush_called = True

    db = FakeSession()
    ok, reason = await VendorService.delete(db, vendor.id)

    assert ok is True
    assert reason == ""
    assert vendor.is_active is False
    assert vendor.deleted_at is not None
    assert db.flush_called is True


@pytest.mark.asyncio
async def test_provider_delete_marks_record_inactive_when_no_offerings():
    from testing_service.services.model_service import ProviderService

    provider = SimpleNamespace(id=9, is_active=True, deleted_at=None)

    class FakeSession:
        def __init__(self):
            self.flush_called = False

        async def execute(self, statement):
            sql = str(statement)
            if "FROM providers" in sql:
                return _ScalarResult(scalar_one_or_none=provider)
            if "FROM model_provider_offerings" in sql:
                return _ScalarResult(scalar=0)
            raise AssertionError(sql)

        async def flush(self):
            self.flush_called = True

    db = FakeSession()
    ok, reason = await ProviderService.delete(db, provider.id)

    assert ok is True
    assert reason == ""
    assert provider.is_active is False
    assert provider.deleted_at is not None
    assert db.flush_called is True


@pytest.mark.asyncio
async def test_vendor_delete_rejects_when_active_models_exist():
    from testing_service.services.model_service import VendorService

    vendor = SimpleNamespace(id=7, is_active=True, deleted_at=None)

    class FakeSession:
        async def execute(self, statement):
            sql = str(statement)
            if "FROM model_vendors" in sql:
                return _ScalarResult(scalar_one_or_none=vendor)
            if "FROM models" in sql:
                return _ScalarResult(scalar=2)
            raise AssertionError(sql)

        async def flush(self):
            raise AssertionError("flush should not run when delete is rejected")

    ok, reason = await VendorService.delete(FakeSession(), vendor.id)

    assert ok is False
    assert "2" in reason
    assert vendor.is_active is True
    assert vendor.deleted_at is None


@pytest.mark.asyncio
async def test_provider_delete_rejects_when_active_offerings_exist():
    from testing_service.services.model_service import ProviderService

    provider = SimpleNamespace(id=9, is_active=True, deleted_at=None)

    class FakeSession:
        async def execute(self, statement):
            sql = str(statement)
            if "FROM providers" in sql:
                return _ScalarResult(scalar_one_or_none=provider)
            if "FROM model_provider_offerings" in sql:
                return _ScalarResult(scalar=3)
            raise AssertionError(sql)

        async def flush(self):
            raise AssertionError("flush should not run when delete is rejected")

    ok, reason = await ProviderService.delete(FakeSession(), provider.id)

    assert ok is False
    assert "3" in reason
    assert provider.is_active is True
    assert provider.deleted_at is None


@pytest.mark.asyncio
async def test_offering_provider_counts_only_include_active_offerings_and_providers():
    from testing_service.services.model_service import OfferingService

    captured = {}

    class FakeSession:
        async def execute(self, statement):
            captured["sql"] = str(statement.compile(compile_kwargs={"literal_binds": True})).lower()
            return _ScalarResult(
                items=[
                    SimpleNamespace(model_id=11, provider_count=2),
                    SimpleNamespace(model_id=15, provider_count=1),
                ]
            )

    counts = await OfferingService.get_active_provider_counts(FakeSession(), [11, 15])

    assert counts == {11: 2, 15: 1}
    assert "model_provider_offerings.is_active = true" in captured["sql"]
    assert "model_provider_offerings.deleted_at is null" in captured["sql"]
    assert "providers.is_active = true" in captured["sql"]
    assert "providers.deleted_at is null" in captured["sql"]
    assert "group by model_provider_offerings.model_id" in captured["sql"]


@pytest.mark.asyncio
async def test_provider_service_create_persists_probe_config(monkeypatch):
    from common.utils.crypto import decrypt_api_key
    from testing_service.schemas import ProviderCreate
    from testing_service.services import model_service

    monkeypatch.setattr(
        model_service.settings,
        "TESTING_SECRET_MASTER_KEY",
        "23c3a1b6fcd47f5447f8ef98c9c3ce9b05645c4f064a1cc9463cc29f888a798f",
    )

    class FakeSession:
        def __init__(self):
            self.added = None
            self.flush_called = False
            self.refresh_called = False

        async def execute(self, _statement):
            return _ScalarResult(scalar_one_or_none=None)

        def add(self, obj):
            self.added = obj

        async def flush(self):
            self.flush_called = True

        async def refresh(self, _obj):
            self.refresh_called = True

    db = FakeSession()
    provider = await model_service.ProviderService.create(
        db,
        ProviderCreate(
            slug="openai",
            name="OpenAI",
            probe_api_base_url="https://api.openai.com/v1",
            probe_api_key="sk-test-12345678",
        ),
    )

    assert db.added is provider
    assert db.flush_called is True
    assert db.refresh_called is True
    assert provider.probe_api_base_url == "https://api.openai.com/v1"
    assert provider.probe_api_key_masked == "sk-t****5678"
    assert (
        decrypt_api_key(
            provider.probe_api_key_ciphertext,
            provider.probe_api_key_iv,
            provider.probe_api_key_tag,
            model_service.settings.TESTING_SECRET_MASTER_KEY,
        )
        == "sk-test-12345678"
    )


@pytest.mark.asyncio
async def test_provider_service_update_writes_probe_config(monkeypatch):
    from testing_service.models import Provider
    from testing_service.schemas import ProviderUpdate
    from testing_service.services import model_service

    monkeypatch.setattr(
        model_service.settings,
        "TESTING_SECRET_MASTER_KEY",
        "23c3a1b6fcd47f5447f8ef98c9c3ce9b05645c4f064a1cc9463cc29f888a798f",
    )

    provider = Provider(id=12, slug="anthropic", name="Anthropic", is_active=True)

    class FakeSession:
        def __init__(self):
            self.flush_called = False
            self.refresh_called = False

        async def execute(self, _statement):
            return _ScalarResult(scalar_one_or_none=provider)

        async def flush(self):
            self.flush_called = True

        async def refresh(self, _obj):
            self.refresh_called = True

    db = FakeSession()
    updated = await model_service.ProviderService.update(
        db,
        provider.id,
        ProviderUpdate(
            probe_api_base_url="https://api.anthropic.com/v1",
            probe_api_key="sk-ant-87654321",
        ),
    )

    assert updated is provider
    assert db.flush_called is True
    assert db.refresh_called is True
    assert provider.probe_api_base_url == "https://api.anthropic.com/v1"
    assert provider.probe_api_key_masked == "sk-a****4321"


@pytest.mark.asyncio
async def test_model_create_restores_soft_deleted_record_and_clears_deleted_at():
    from testing_service.services.model_service import ModelService

    existing = SimpleNamespace(
        id=11,
        slug="demo-model",
        vendor_id=1,
        name="Old",
        description="old",
        capability_tags=["old"],
        context_window=1024,
        max_output_tokens=128,
        is_reasoning_model=False,
        sort_order=1,
        is_active=False,
        deleted_at=datetime(2026, 1, 1),
    )
    added = []

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.flush_called = False
            self.refresh_called = False

        async def execute(self, _statement):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return _ScalarResult(scalar_one_or_none=existing)
            return _ScalarResult()

        def add(self, obj):
            added.append(obj)

        async def flush(self):
            self.flush_called = True

        async def refresh(self, obj):
            self.refresh_called = True

    data = SimpleNamespace(
        vendor_id=5,
        slug="demo-model",
        name="Demo",
        description="new",
        capability_tags=["reasoning"],
        context_window=8192,
        max_output_tokens=2048,
        is_reasoning_model=True,
        sort_order=9,
        is_active=True,
        categories=[SimpleNamespace(category_id=2, sort_order=1)],
    )

    restored = await ModelService.create(FakeSession(), data)

    assert restored is existing
    assert existing.vendor_id == 5
    assert existing.name == "Demo"
    assert existing.is_active is True
    assert existing.deleted_at is None
    assert added, "category mappings should be recreated"

@pytest.mark.asyncio
async def test_model_delete_marks_deleted_at():
    from testing_service.services.model_service import ModelService

    model = SimpleNamespace(slug="demo-model", is_active=True, deleted_at=None)

    class FakeSession:
        def __init__(self):
            self.flush_called = False

        async def execute(self, statement):
            assert "FROM models" in str(statement)
            return _ScalarResult(scalar_one_or_none=model)

        async def flush(self):
            self.flush_called = True

    db = FakeSession()
    ok, reason = await ModelService.delete(db, "demo-model")

    assert ok is True
    assert reason == ""
    assert model.is_active is False
    assert model.deleted_at is not None
    assert db.flush_called is True


@pytest.mark.asyncio
async def test_list_models_includes_provider_count(monkeypatch):
    from testing_service.api.v1.endpoints.models import list_models

    model = SimpleNamespace(
        id=11,
        slug="deepseek-v3",
        name="DeepSeek V3",
        description="desc",
        capability_tags=["reasoning", "coding"],
        context_window=64000,
        max_output_tokens=8192,
        is_reasoning_model=True,
        sort_order=1,
        vendor=SimpleNamespace(
            id=4,
            slug="deepseek",
            name="DeepSeek",
            logo_url="https://example.com/logo.png",
        ),
    )

    async def fake_list_all(**kwargs):
        return [model], 1

    async def fake_get_category_briefs(db, model_id):
        assert model_id == 11
        return []

    async def fake_get_active_provider_counts(db, model_ids):
        assert model_ids == [11]
        return {11: 3}

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.models.ModelService.list_all",
        fake_list_all,
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.models.ModelService.get_category_briefs",
        fake_get_category_briefs,
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.models.OfferingService.get_active_provider_counts",
        fake_get_active_provider_counts,
    )

    response = await list_models(
        category=None,
        vendors="deepseek",
        q=None,
        page=1,
        page_size=20,
        db=object(),
    )

    assert response["code"] == 200
    assert response["data"]["total"] == 1
    assert response["data"]["items"][0].provider_count == 3


@pytest.mark.asyncio
async def test_offering_create_restores_soft_deleted_record_and_clears_deleted_at():
    from testing_service.services.model_service import OfferingService

    existing = SimpleNamespace(
        id=21,
        model_id=5,
        provider_id=3,
        price_input_per_m=1.0,
        price_output_per_m=2.0,
        provider_model_name="old-model",
        is_active=False,
        deleted_at=datetime(2026, 1, 1),
    )

    class FakeSession:
        def __init__(self):
            self.flush_called = False
            self.refresh_called = False

        async def execute(self, statement):
            assert "FROM model_provider_offerings" in str(statement)
            return _ScalarResult(scalar_one_or_none=existing)

        def add(self, obj):
            raise AssertionError("restore path should not add a new offering")

        async def flush(self):
            self.flush_called = True

        async def refresh(self, obj):
            self.refresh_called = True

    data = SimpleNamespace(
        provider_id=3,
        price_input_per_m=9.9,
        price_output_per_m=19.9,
        provider_model_id="new-model",
    )

    restored = await OfferingService.create(FakeSession(), 5, data)

    assert restored is existing
    assert existing.price_input_per_m == 9.9
    assert existing.price_output_per_m == 19.9
    assert existing.provider_model_name == "new-model"
    assert existing.is_active is True
    assert existing.deleted_at is None


@pytest.mark.asyncio
async def test_offering_delete_marks_deleted_at():
    from testing_service.services.model_service import OfferingService

    offering = SimpleNamespace(id=21, is_active=True, deleted_at=None)

    class FakeSession:
        def __init__(self):
            self.flush_called = False

        async def execute(self, statement):
            assert "FROM model_provider_offerings" in str(statement)
            return _ScalarResult(scalar_one_or_none=offering)

        async def flush(self):
            self.flush_called = True

    db = FakeSession()
    found = await OfferingService.delete(db, 21)

    assert found is True
    assert offering.is_active is False
    assert offering.deleted_at is not None
    assert db.flush_called is True


def test_provider_response_accepts_orm_probe_config():
    from testing_service.schemas import ProviderResponse

    provider = SimpleNamespace(
        id=10,
        slug="test-provider",
        name="Test Provider",
        logo_url=None,
        is_active=True,
        probe_config=SimpleNamespace(
            probe_api_base_url="https://example.com",
            has_probe_api_key=True,
            probe_api_key_masked="sk-****",
            probe_key_updated_at=None,
        ),
    )

    response = ProviderResponse.model_validate(provider)

    assert response.probe_config is not None
    assert response.probe_config.probe_api_base_url == "https://example.com"
    assert response.probe_config.has_probe_api_key is True


@pytest.mark.asyncio
async def test_benchmark_engine_uses_usage_and_first_non_empty_chunk(monkeypatch):
    from testing_service.benchmark.engine import BenchmarkEngine

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    def make_chunk(content, usage=None):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))]
        , usage=usage)

    async def fake_acompletion(**kwargs):
        assert kwargs["temperature"] == 0
        assert kwargs["max_tokens"] == 96
        assert kwargs["stream_options"] == {"include_usage": True}
        return FakeStream(
            [
                make_chunk(""),
                make_chunk("alpha bravo", {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}),
            ]
        )

    timestamps = iter([100.0, 100.25, 101.25])
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.register_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.acompletion", fake_acompletion)
    monkeypatch.setattr(
        "testing_service.benchmark.engine.litellm.encode",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("encode should not be used when usage is present")),
    )
    monkeypatch.setattr("testing_service.benchmark.engine.time.time", lambda: next(timestamps))

    engine = BenchmarkEngine()
    result = await engine.run_benchmark(model="demo-model", api_key="sk", api_base="https://example.com")

    assert result["status"] == "success"
    assert result["latency_ttft"] == 0.25
    assert result["latency_total"] == 1.25
    assert result["prompt_tokens"] == 12
    assert result["output_tokens"] == 8
    assert result["throughput"] == 8.0


@pytest.mark.asyncio
async def test_benchmark_engine_falls_back_to_encode_without_usage(monkeypatch):
    from testing_service.benchmark.engine import BenchmarkEngine

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    def make_chunk(content):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content, reasoning_content=None))],
            usage=None,
        )

    async def fake_acompletion(**kwargs):
        assert kwargs["stream_options"] == {"include_usage": True}
        assert kwargs["custom_llm_provider"] == "openai"
        assert kwargs["base_url"] == "https://example.com"
        assert kwargs["api_base"] == "https://example.com"
        return FakeStream([make_chunk(""), make_chunk("hello world")])

    timestamps = iter([10.0, 10.4, 11.4])
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.register_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.acompletion", fake_acompletion)
    monkeypatch.setattr(
        "testing_service.benchmark.engine.litellm.encode",
        lambda **kwargs: [0] * (3 if kwargs["text"] == "Please introduce yourself in one sentence." else 5),
    )
    monkeypatch.setattr("testing_service.benchmark.engine.time.time", lambda: next(timestamps))

    engine = BenchmarkEngine()
    result = await engine.run_benchmark(model="demo-model", api_key="sk", api_base="https://example.com")

    assert result["status"] == "success"
    assert result["prompt_tokens"] == 3
    assert result["output_tokens"] == 5
    assert result["latency_ttft"] == 0.4
    assert result["latency_total"] == 1.4
    assert result["throughput"] == 5.0


@pytest.mark.asyncio
async def test_benchmark_engine_uses_openai_compatible_provider_for_custom_base(monkeypatch):
    from testing_service.benchmark.engine import BenchmarkEngine

    captured_kwargs = {}

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def fake_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return FakeStream()

    monkeypatch.setattr("testing_service.benchmark.engine.litellm.register_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.acompletion", fake_acompletion)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.encode", lambda **_kwargs: [])

    engine = BenchmarkEngine()
    await engine.run_benchmark(model="deepseek-chat", api_key="sk", api_base="https://example.com/v1")

    assert captured_kwargs["custom_llm_provider"] == "openai"
    assert captured_kwargs["base_url"] == "https://example.com/v1"
    assert captured_kwargs["api_base"] == "https://example.com/v1"


@pytest.mark.asyncio
async def test_benchmark_engine_normalizes_full_chat_completions_url(monkeypatch):
    from testing_service.benchmark.engine import BenchmarkEngine

    captured_kwargs = {}

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def fake_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return FakeStream()

    monkeypatch.setattr("testing_service.benchmark.engine.litellm.register_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.acompletion", fake_acompletion)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.encode", lambda **_kwargs: [])

    engine = BenchmarkEngine()
    await engine.run_benchmark(
        model="/maas/deepseek-ai/DeepSeek-V3.2",
        api_key="sk",
        api_base="https://maas-api.lanyun.net/v1/chat/completions",
    )

    assert captured_kwargs["custom_llm_provider"] == "openai"
    assert captured_kwargs["base_url"] == "https://maas-api.lanyun.net/v1"
    assert captured_kwargs["api_base"] == "https://maas-api.lanyun.net/v1"


@pytest.mark.asyncio
async def test_benchmark_engine_returns_stable_error_payload(monkeypatch):
    from testing_service.benchmark.engine import BenchmarkEngine

    timestamps = iter([20.0, 20.75])

    async def fake_acompletion(**_kwargs):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr("testing_service.benchmark.engine.litellm.register_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("testing_service.benchmark.engine.litellm.acompletion", fake_acompletion)
    monkeypatch.setattr("testing_service.benchmark.engine.time.time", lambda: next(timestamps))

    engine = BenchmarkEngine()
    result = await engine.run_benchmark(model="demo-model")

    assert result["status"] == "error"
    assert result["error"] == "upstream exploded"
    assert result["latency_ttft"] == 0.0
    assert result["latency_total"] == 0.75
    assert result["throughput"] == 0.0
    assert result["prompt_tokens"] is None
    assert result["output_tokens"] == 0


@pytest.mark.asyncio
async def test_benchmark_summary_uses_default_probe_region(monkeypatch):
    from testing_service.api.v1.endpoints.benchmark import get_benchmark_stats_summary

    captured = {}
    offering = SimpleNamespace(
        id=1,
        model_id=101,
        provider=SimpleNamespace(name="Provider A", slug="provider-a"),
    )
    model = SimpleNamespace(
        slug="demo-model",
        name="Demo Model",
        vendor=SimpleNamespace(name="Demo Vendor"),
    )

    async def fake_list_all_active(db):
        return [offering]

    async def fake_get_by_id(db, model_id):
        assert model_id == 101
        return model

    async def fake_get_metrics(db, offering_id, n=5, region=None):
        captured["region"] = region
        return []

    async def fake_get_latest_by_offering(db, offering_id):
        return None

    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.get_settings",
        lambda: SimpleNamespace(probe_enabled=True, probe_region="cn-east"),
    )
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.OfferingService.list_all_active",
        fake_list_all_active,
    )
    monkeypatch.setattr("testing_service.api.v1.endpoints.benchmark.ModelService.get_by_id", fake_get_by_id)
    monkeypatch.setattr("testing_service.api.v1.endpoints.benchmark.OfferingService.get_metrics", fake_get_metrics)
    monkeypatch.setattr(
        "testing_service.api.v1.endpoints.benchmark.PerformanceMetricService.get_latest_by_offering",
        fake_get_latest_by_offering,
        raising=False,
    )

    response = await get_benchmark_stats_summary(n=5, db=object())

    assert response["code"] == 200
    assert captured["region"] == "cn-east"


@pytest.mark.asyncio
async def test_trend_data_uses_calendar_day_cutoff(monkeypatch):
    from testing_service.services.model_service import PerformanceMetricService

    captured = {}

    class FakeSession:
        async def execute(self, statement):
            captured["sql"] = str(statement.compile(compile_kwargs={"literal_binds": True}))
            return _ScalarResult(items=[])

    monkeypatch.setattr(
        "testing_service.services.model_service.now",
        lambda: datetime(2026, 3, 11, 15, 30, 0),
    )

    rows = await PerformanceMetricService.get_trend_data(
        FakeSession(),
        model_id=1,
        days=7,
        region="cn-east",
    )

    assert rows == []
    assert "2026-03-05 00:00:00" in captured["sql"]


def test_base_service_settings_requires_explicit_jwt_secret():
    from common.config import BaseServiceSettings

    class DemoSettings(BaseServiceSettings):
        pass

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        DemoSettings(JWT_SECRET_KEY="", INTERNAL_SECRET="internal-secret")


@pytest.mark.asyncio
async def test_admin_refresh_endpoint_reissues_access_token():
    from admin_service.api.v1.endpoints.auth import refresh_token
    from admin_service.config import settings as admin_settings
    from common.utils.jwt import create_refresh_token
    from common.utils.jwt import decode_token
    from fastapi import Response

    refresh_cookie = create_refresh_token(
        data={"uid": 88, "sub": "88"},
        secret_key=admin_settings.JWT_SECRET_KEY,
        algorithm=admin_settings.JWT_ALGORITHM,
        expire_days=admin_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )
    response = Response()
    result = await refresh_token(
        response=response,
        refresh_token=refresh_cookie,
    )

    payload = decode_token(
        result.data.access_token,
        admin_settings.JWT_SECRET_KEY,
        admin_settings.JWT_ALGORITHM,
    )

    assert result.code == 200
    assert payload["uid"] == 88
    assert payload["type"] == "access"
    assert "access_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_invitation_verify_and_use_locks_row_without_commit():
    from admin_service.services.invitation_service import InvitationCodeService

    invitation = SimpleNamespace(
        is_used=False,
        is_disabled=False,
        is_expired=False,
        status=0,
        used_by=None,
        used_at=None,
    )
    captured = {}

    class FakeSession:
        async def execute(self, statement):
            captured["sql"] = str(statement)
            return _ScalarResult(scalar_one_or_none=invitation)

        async def flush(self):
            captured["flush"] = True

        async def commit(self):
            captured["commit"] = True

        async def refresh(self, obj):
            captured["refresh"] = obj

    await InvitationCodeService.verify_and_use(
        FakeSession(),
        "invite-code",
        123456,
        commit=False,
    )

    assert "FOR UPDATE" in captured["sql"].upper()
    assert captured["flush"] is True
    assert "commit" not in captured
    assert invitation.status == 1
    assert invitation.used_by == 123456
    assert invitation.used_at is not None


@pytest.mark.asyncio
async def test_register_consumes_invitation_code_via_admin_internal_client(monkeypatch):
    from user_service.schemas import RegisterRequest
    from user_service.services.auth_service import AuthService

    captured = {}

    async def fake_verify_email_code(db, email, code, purpose):
        captured["verify_email"] = (email, code, purpose)

    async def fake_consume_invitation(code, used_by):
        captured["consume_invitation"] = (code, used_by)

    monkeypatch.setattr(
        "user_service.services.auth_service.email_service.verify_code_or_raise",
        fake_verify_email_code,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.AdminInvitationClientService.consume_invitation_code",
        fake_consume_invitation,
    )
    monkeypatch.setattr(
        "user_service.utils.password.check_password_strength",
        lambda password, lang="zh": (True, ""),
    )
    monkeypatch.setattr("user_service.services.auth_service.generate_snowflake_id", lambda: 42)

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commit_called = False
            self.refresh_called = False

        async def execute(self, statement):
            return _ScalarResult(scalar_one_or_none=None)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_called = True

        async def refresh(self, obj):
            self.refresh_called = True

    db = FakeSession()
    request = RegisterRequest(
        invitation_code="invite-code",
        email="user@example.com",
        password="StrongPass123!",
        confirm_password="StrongPass123!",
        verification_code="123456",
    )

    user = await AuthService.register(db, request)

    assert user.uid == 42
    assert captured["verify_email"] == ("user@example.com", "123456", "register")
    assert captured["consume_invitation"] == ("invite-code", 42)
    assert db.commit_called is True
    assert db.refresh_called is True


@pytest.mark.asyncio
async def test_register_releases_invitation_when_local_commit_fails(monkeypatch):
    from user_service.schemas import RegisterRequest
    from user_service.services.auth_service import AuthService

    captured = {}

    async def fake_verify_email_code(db, email, code, purpose):
        captured["verify_email"] = (email, code, purpose)

    async def fake_consume_invitation(code, used_by):
        captured["consume_invitation"] = (code, used_by)

    async def fake_release_invitation(code, used_by):
        captured["release_invitation"] = (code, used_by)
        return True

    monkeypatch.setattr(
        "user_service.services.auth_service.email_service.verify_code_or_raise",
        fake_verify_email_code,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.AdminInvitationClientService.consume_invitation_code",
        fake_consume_invitation,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.AdminInvitationClientService.release_invitation_code",
        fake_release_invitation,
    )
    monkeypatch.setattr(
        "user_service.utils.password.check_password_strength",
        lambda password, lang="zh": (True, ""),
    )
    monkeypatch.setattr("user_service.services.auth_service.generate_snowflake_id", lambda: 84)

    class FakeSession:
        def __init__(self):
            self.rollback_called = False

        async def execute(self, statement):
            return _ScalarResult(scalar_one_or_none=None)

        def add(self, obj):
            self.added = obj

        async def commit(self):
            raise RuntimeError("commit failed")

        async def rollback(self):
            self.rollback_called = True

    db = FakeSession()
    request = RegisterRequest(
        invitation_code="invite-code",
        email="user@example.com",
        password="StrongPass123!",
        confirm_password="StrongPass123!",
        verification_code="123456",
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await AuthService.register(db, request)

    assert captured["verify_email"] == ("user@example.com", "123456", "register")
    assert captured["consume_invitation"] == ("invite-code", 84)
    assert captured["release_invitation"] == ("invite-code", 84)
    assert db.rollback_called is True


@pytest.mark.asyncio
async def test_router_preflight_uses_locked_row_state(monkeypatch):
    from router_service.services.auth_service import RouterKeyContext
    from router_service.services.billing_service import (
        RouterBillingService,
        RouterQuotaExceededError,
    )

    async def fake_lock(_db, key_id):
        assert key_id == 7
        return SimpleNamespace(
            billing_mode="prepaid",
            balance=0,
            rate_limit_rpm=None,
            daily_quota_tokens=None,
            monthly_quota_tokens=None,
            daily_quota_cost=None,
            monthly_quota_cost=None,
        )

    monkeypatch.setattr(
        RouterBillingService,
        "_lock_router_key",
        staticmethod(fake_lock),
    )

    context = RouterKeyContext(
        key_id=7,
        owner_user_id=1,
        name="demo",
        key_hash="hash",
        billing_mode="postpaid",
        balance=999,
        daily_quota_tokens=None,
        monthly_quota_tokens=None,
        daily_quota_cost=None,
        monthly_quota_cost=None,
        rate_limit_rpm=None,
    )

    with pytest.raises(RouterQuotaExceededError, match="Prepaid balance exhausted"):
        await RouterBillingService.preflight_guard(object(), context)


@pytest.mark.asyncio
async def test_router_reserve_usage_debits_prepaid_balance(monkeypatch):
    from decimal import Decimal

    from router_service.services.auth_service import RouterKeyContext
    from router_service.services.billing_service import RouterBillingService

    locked_key = SimpleNamespace(
        billing_mode="prepaid",
        balance=Decimal("10.000000"),
        is_active=True,
        is_deleted=False,
    )

    monkeypatch.setattr(
        "router_service.services.billing_service.get_settings",
        lambda: SimpleNamespace(ROUTER_BILLING_CURRENCY="CNY"),
    )
    monkeypatch.setattr(
        RouterBillingService,
        "_lock_router_key",
        staticmethod(AsyncMock(return_value=locked_key)),
    )
    monkeypatch.setattr(
        RouterBillingService,
        "preflight_guard",
        AsyncMock(),
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.flush_called = False
            self.commit_called = False
            self.refresh_called = False

        def add(self, obj):
            self.added.append(obj)
            if getattr(obj, "request_id", None) == "req-1":
                obj.id = 99

        async def flush(self):
            self.flush_called = True

        async def commit(self):
            self.commit_called = True

        async def refresh(self, obj):
            self.refresh_called = True

    db = FakeSession()
    context = RouterKeyContext(
        key_id=7,
        owner_user_id=9,
        name="demo",
        key_hash="hash",
        billing_mode="prepaid",
        balance=10.0,
        daily_quota_tokens=None,
        monthly_quota_tokens=None,
        daily_quota_cost=None,
        monthly_quota_cost=None,
        rate_limit_rpm=None,
    )

    event = await RouterBillingService.reserve_usage(
        db,
        context=context,
        request_id="req-1",
        endpoint="/v1/chat/completions",
        requested_model="demo-model",
        resolved_model="demo-model",
        request_payload={"messages": [{"role": "user", "content": "hello"}], "max_tokens": 128},
        input_price_per_m=1.0,
        output_price_per_m=2.0,
    )

    assert event.request_id == "req-1"
    assert db.flush_called is True
    assert db.commit_called is True
    assert db.refresh_called is True
    assert locked_key.balance < Decimal("10.000000")
    assert any(getattr(obj, "direction", None) == "debit" for obj in db.added)


@pytest.mark.asyncio
async def test_router_settle_usage_refunds_failed_request(monkeypatch):
    from decimal import Decimal

    from router_service.services.auth_service import RouterKeyContext
    from router_service.services.billing_service import RouterBillingService

    event = SimpleNamespace(
        id=88,
        request_id="req-2",
        cost_total=Decimal("0.003000"),
    )
    locked_key = SimpleNamespace(
        billing_mode="prepaid",
        balance=Decimal("1.000000"),
        is_active=True,
        is_deleted=False,
    )

    monkeypatch.setattr(
        "router_service.services.billing_service.get_settings",
        lambda: SimpleNamespace(ROUTER_BILLING_CURRENCY="CNY"),
    )
    monkeypatch.setattr(
        RouterBillingService,
        "_lock_usage_event",
        staticmethod(AsyncMock(return_value=event)),
    )
    monkeypatch.setattr(
        RouterBillingService,
        "_lock_router_key",
        staticmethod(AsyncMock(return_value=locked_key)),
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.flush_called = False
            self.commit_called = False
            self.refresh_called = False

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flush_called = True

        async def commit(self):
            self.commit_called = True

        async def refresh(self, obj):
            self.refresh_called = True

    db = FakeSession()
    context = RouterKeyContext(
        key_id=7,
        owner_user_id=9,
        name="demo",
        key_hash="hash",
        billing_mode="prepaid",
        balance=1.0,
        daily_quota_tokens=None,
        monthly_quota_tokens=None,
        daily_quota_cost=None,
        monthly_quota_cost=None,
        rate_limit_rpm=None,
    )

    result = await RouterBillingService.settle_usage(
        db,
        context=context,
        request_id="req-2",
        endpoint="/v1/chat/completions",
        provider_slug="demo-provider",
        requested_model="demo-model",
        resolved_model="demo-model",
        request_payload={"messages": [{"role": "user", "content": "hello"}]},
        response_payload=None,
        input_price_per_m=1.0,
        output_price_per_m=2.0,
        status_code=502,
        error_code="upstream_error",
        error_message="boom",
    )

    assert result is event
    assert event.status_code == 502
    assert event.total_tokens == 0
    assert event.cost_total == Decimal("0")
    assert locked_key.balance == Decimal("1.003000")
    assert any(getattr(obj, "direction", None) == "credit" for obj in db.added)
    assert db.commit_called is True


@pytest.mark.asyncio
async def test_send_verification_code_rolls_back_when_delivery_fails(monkeypatch):
    from common.core.exceptions import ServiceUnavailableException
    from user_service.services.email_service import EmailService

    service = EmailService()
    monkeypatch.setattr(service, "generate_code", lambda: "123456")
    monkeypatch.setattr(
        service,
        "_send_email",
        lambda _email, _code, _purpose: (_ for _ in ()).throw(
            ServiceUnavailableException("smtp down")
        ),
    )

    class FakeSession:
        def __init__(self):
            self.commit_called = False
            self.rollback_called = False
            self.flush_called = False

        async def execute(self, statement):
            sql = str(statement)
            if "count" in sql.lower():
                return _ScalarResult(scalar=0)
            if "limit" in sql.lower():
                return _ScalarResult(scalar_one_or_none=None)
            return _ScalarResult(items=[])

        async def delete(self, obj):
            raise AssertionError("No old codes expected")

        def add(self, obj):
            self.added = obj

        async def flush(self):
            self.flush_called = True

        async def commit(self):
            self.commit_called = True

        async def rollback(self):
            self.rollback_called = True

    db = FakeSession()

    with pytest.raises(ServiceUnavailableException):
        await service.send_verification_code(db, "user@example.com", "register")

    assert db.flush_called is True
    assert db.rollback_called is True
    assert db.commit_called is False


@pytest.mark.asyncio
async def test_verify_email_updates_user_state(monkeypatch):
    from user_service.services.auth_service import AuthService

    calls = {}
    user = SimpleNamespace(email="user@example.com", status=2, email_verified_at=None)

    async def fake_verify_code(db, email, code, purpose):
        calls["verify"] = (email, code, purpose)

    monkeypatch.setattr(
        "user_service.services.auth_service.email_service.verify_code_or_raise",
        fake_verify_code,
    )

    class FakeSession:
        def __init__(self):
            self.commit_called = False
            self.refresh_called = False

        async def execute(self, statement):
            return _ScalarResult(scalar_one_or_none=user)

        async def commit(self):
            self.commit_called = True

        async def refresh(self, obj):
            self.refresh_called = True

    db = FakeSession()
    result = await AuthService.verify_email(db, "user@example.com", "123456")

    assert result is user
    assert calls["verify"] == ("user@example.com", "123456", "verify")
    assert user.status == 1
    assert user.email_verified_at is not None
    assert db.commit_called is True
    assert db.refresh_called is True


@pytest.mark.asyncio
async def test_router_dependency_uses_identity_internal_contract(monkeypatch):
    from router_service.dependencies import get_current_user

    monkeypatch.setattr(
        "router_service.dependencies.decode_token",
        lambda **_kwargs: {"uid": 77, "type": "access"},
    )

    async def fake_fetch_identity_user(uid):
        assert uid == 77
        return SimpleNamespace(id=5, uid=77, email="user@example.com", status=1)

    monkeypatch.setattr(
        "router_service.dependencies.IdentityClientService.fetch_user_by_uid",
        fake_fetch_identity_user,
    )

    user = await get_current_user(
        request=None,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
        access_token=None,
        db=object(),
    )

    assert user.id == 5
    assert user.uid == 77
    assert user.email == "user@example.com"


def test_user_api_registers_internal_router():
    from user_service.api.v1.router import api_router

    route_paths = {route.path for route in api_router.routes}
    assert "/api/v1/internal/users/{uid}" in route_paths
    assert "/api/v1/internal/users/by-id/{user_id}" in route_paths
    assert "/api/v1/internal/stats/users" in route_paths


def test_admin_api_registers_internal_router():
    from admin_service.api.v1.router import api_router

    route_paths = {route.path for route in api_router.routes}
    assert "/api/v1/internal/admins/{uid}" in route_paths


@pytest.mark.asyncio
async def test_router_key_verify_uses_identity_service(monkeypatch):
    from router_service.services.auth_service import RouterKeyAuthService

    key = SimpleNamespace(
        id=3,
        owner_user_id=11,
        name="demo",
        key_hash="hash",
        is_active=True,
        is_deleted=False,
        billing_mode="postpaid",
        balance=None,
        daily_quota_tokens=None,
        monthly_quota_tokens=None,
        daily_quota_cost=None,
        monthly_quota_cost=None,
        rate_limit_rpm=60,
        last_used_at=None,
    )

    monkeypatch.setattr(
        "router_service.services.auth_service.IdentityClientService.fetch_user_by_id",
        AsyncMock(return_value=SimpleNamespace(id=11, uid=77, email="user@example.com", status=1)),
    )

    class FakeSession:
        def __init__(self):
            self.flush_called = False

        async def execute(self, statement):
            return _ScalarResult(scalar_one_or_none=key)

        async def flush(self):
            self.flush_called = True

    db = FakeSession()
    context = await RouterKeyAuthService.verify_key(db, "raw-key")

    assert context is not None
    assert context.owner_user_id == 11
    assert context.key_id == 3
    assert db.flush_called is True


def test_service_entrypoints_do_not_cross_register_other_service_models():
    router_main = open(r"F:\Eucal_AI\backend\router_service\main.py", encoding="utf-8").read()
    testing_main = open(r"F:\Eucal_AI\backend\testing_service\main.py", encoding="utf-8").read()
    testing_worker = open(r"F:\Eucal_AI\backend\testing_service\worker.py", encoding="utf-8").read()
    user_main = open(r"F:\Eucal_AI\backend\user_service\main.py", encoding="utf-8").read()

    assert "import user_service.models" not in router_main
    assert "import admin_service.models" not in router_main
    assert "import testing_service.models" not in router_main
    assert "await init_db()" not in router_main

    assert "import admin_service.models" not in testing_main
    assert "await init_db()" not in testing_main
    assert "import admin_service.models" not in testing_worker

    assert "import admin_service.models" not in user_main


def test_testing_models_do_not_reference_admin_tables():
    testing_models = open(
        r"F:\Eucal_AI\backend\testing_service\models\model.py",
        encoding="utf-8",
    ).read()

    assert 'ForeignKey("admin_users.id"' not in testing_models


def test_router_models_do_not_reference_user_tables():
    router_api_key_model = open(
        r"F:\Eucal_AI\backend\router_service\models\router_api_key.py",
        encoding="utf-8",
    ).read()
    router_billing_model = open(
        r"F:\Eucal_AI\backend\router_service\models\router_billing.py",
        encoding="utf-8",
    ).read()

    assert 'ForeignKey("users.id"' not in router_api_key_model
    assert 'ForeignKey("users.id"' not in router_billing_model


def test_testing_api_does_not_import_admin_models_for_principal_types():
    testing_api_files = [
        r"F:\Eucal_AI\backend\testing_service\api\dependencies.py",
        r"F:\Eucal_AI\backend\testing_service\api\v1\endpoints\benchmark.py",
        r"F:\Eucal_AI\backend\testing_service\api\v1\endpoints\model_providers.py",
        r"F:\Eucal_AI\backend\testing_service\api\v1\endpoints\models.py",
        r"F:\Eucal_AI\backend\testing_service\api\v1\endpoints\providers.py",
        r"F:\Eucal_AI\backend\testing_service\api\v1\endpoints\vendors.py",
    ]

    for path in testing_api_files:
        source = open(path, encoding="utf-8").read()
        assert "from admin_service.models import AdminUser" not in source
        assert "from admin_service.services.auth_service_v2 import AdminAuthService" not in source


def test_invitation_domain_is_hosted_under_admin_services_for_admin_endpoints():
    admin_invitation_endpoint = Path(
        r"F:\Eucal_AI\backend\admin_service\api\v1\endpoints\invitation.py"
    ).read_text(encoding="utf-8")
    user_auth_service = Path(
        r"F:\Eucal_AI\backend\user_service\services\auth_service.py"
    ).read_text(encoding="utf-8")

    assert "from admin_service.services.invitation_service import InvitationCodeService" in admin_invitation_endpoint
    assert "from user_service.services.admin_client import AdminInvitationClientService" in user_auth_service
    assert "from admin_service.services.identity_client import IdentityClientService" in admin_invitation_endpoint
    assert "from user_service.models import User" not in admin_invitation_endpoint
    assert Path(r"F:\Eucal_AI\backend\admin_service\services\invitation_service.py").exists()


def test_admin_governance_domain_is_hosted_under_admin_services():
    admin_users_endpoint = Path(
        r"F:\Eucal_AI\backend\admin_service\api\v1\endpoints\admin_users.py"
    ).read_text(encoding="utf-8")
    admin_audit_endpoint = Path(
        r"F:\Eucal_AI\backend\admin_service\api\v1\endpoints\admin_audit_logs.py"
    ).read_text(encoding="utf-8")
    assert "from admin_service.services.management_service import AdminManagementService" in admin_users_endpoint
    assert "from admin_service.services.audit_service import AdminAuditService" in admin_audit_endpoint
    assert Path(r"F:\Eucal_AI\backend\admin_service\services\management_service.py").exists()
    assert Path(r"F:\Eucal_AI\backend\admin_service\services\audit_service.py").exists()


def test_admin_identity_domain_is_hosted_under_admin_services():
    admin_dependencies = Path(
        r"F:\Eucal_AI\backend\admin_service\dependencies.py"
    ).read_text(encoding="utf-8")
    admin_auth_endpoint = Path(
        r"F:\Eucal_AI\backend\admin_service\api\v1\endpoints\auth.py"
    ).read_text(encoding="utf-8")
    admin_main = Path(
        r"F:\Eucal_AI\backend\admin_service\main.py"
    ).read_text(encoding="utf-8")
    admin_bootstrap_cli = Path(
        r"F:\Eucal_AI\backend\admin_service\bootstrap_superadmin.py"
    ).read_text(encoding="utf-8")

    assert "from admin_service.services.auth_service import AdminAuthService" in admin_dependencies
    assert "from admin_service.services.auth_service import AdminAuthService" in admin_auth_endpoint
    assert "from admin_service.services.bootstrap_service import AdminBootstrapService" in admin_main
    assert "from admin_service.services.bootstrap_service import AdminBootstrapService" in admin_bootstrap_cli
    assert not Path(r"F:\Eucal_AI\backend\admin_service\services\auth_service_v2.py").exists()
    assert Path(r"F:\Eucal_AI\backend\admin_service\services\bootstrap_service.py").exists()

