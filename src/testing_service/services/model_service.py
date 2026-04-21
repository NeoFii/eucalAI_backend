# -*- coding: utf-8 -*-
"""
Testing 服务业务逻辑层
提供模型、研发商、服务提供商、报价和性能指标的查询与写入服务
"""

from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.crypto import encrypt_api_key, mask_api_key
from common.utils.timezone import now

from testing_service.config import get_settings
from testing_service.models import (
    ModelCategory,
    ModelVendor,
    Model,
    ModelCategoryMap,
    Provider,
    ModelProviderOffering,
    ProviderPerformanceMetric,
)
from testing_service.schemas import (
    ModelCategoryBrief,
    OfferingMetricsResponse,
)
from testing_service.repositories.model_repository import (
    CategoryRepository,
    ModelRepository,
    OfferingRepository,
    ProviderRepository,
    VendorRepository,
)

settings = get_settings()


def _normalize_optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    normalized = value.strip()
    return normalized or None


def _update_provider_probe_key(provider: Provider, plaintext: object) -> None:
    normalized = _normalize_optional_text(plaintext)
    if not normalized:
        return
    encrypted = encrypt_api_key(normalized, settings.TESTING_SECRET_MASTER_KEY)
    provider.probe_api_key_ciphertext = encrypted["ciphertext"]
    provider.probe_api_key_iv = encrypted["iv"]
    provider.probe_api_key_tag = encrypted["tag"]
    provider.probe_api_key_masked = mask_api_key(normalized)
    provider.probe_key_updated_at = now()


# ========== 研发商服务（model_vendors）==========

class VendorService:
    """研发商服务（创造模型的公司，≠ 服务提供商）"""

    @staticmethod
    async def list_all(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[List[ModelVendor], int]:
        """获取所有研发商（管理端展示，不过滤 is_active），按名称排序，支持分页"""
        return await VendorRepository.list_all(db, page=page, page_size=page_size)

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[ModelVendor]:
        """根据 slug 获取研发商"""
        return await VendorRepository.get_by_slug(db, slug)

    @staticmethod
    async def get_by_id(db: AsyncSession, vendor_id: int) -> Optional[ModelVendor]:
        """根据 ID 获取研发商"""
        return await VendorRepository.get_by_id(db, vendor_id)

    @staticmethod
    async def create(db: AsyncSession, data) -> ModelVendor:
        """
        创建研发商。
        - 若 slug 对应活跃记录 → 抛 ValueError（409）
        - 若 slug 对应软删除记录（is_active=False）→ 复用并更新字段
        - 否则 → 创建新记录
        """
        existing = await VendorRepository.get_any_by_slug(db, data.slug)
        if existing:
            if existing.is_active:
                raise ValueError(f"slug '{data.slug}' 已存在")
            existing.name = data.name
            existing.logo_url = data.logo_url
            existing.is_active = data.is_active
            existing.deleted_at = None
            await db.flush()
            await db.refresh(existing)
            return existing
        vendor = ModelVendor(
            slug=data.slug,
            name=data.name,
            logo_url=data.logo_url,
            is_active=data.is_active,
        )
        db.add(vendor)
        await db.flush()
        await db.refresh(vendor)
        return vendor

    @staticmethod
    async def update(db: AsyncSession, vendor_id: int, data) -> Optional[ModelVendor]:
        """更新研发商，仅更新非 None 字段"""
        vendor = await VendorRepository.get_any_by_id(db, vendor_id)
        if not vendor:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(vendor, field, value)
        await db.flush()
        await db.refresh(vendor)
        return vendor

    @staticmethod
    async def delete(db: AsyncSession, vendor_id: int) -> tuple[bool, str]:
        """
        软删除研发商（设置 is_active=False）。
        若存在关联 Model 则拒绝，防止模型引用无效研发商。
        返回 (True, "") 表示成功，(False, 原因) 表示失败。
        """
        vendor = await VendorRepository.get_any_by_id(db, vendor_id)
        if not vendor:
            return False, "not_found"
        model_count = await VendorRepository.count_active_models(db, vendor_id)
        if model_count > 0:
            return False, f"该研发商下存在 {model_count} 个模型，请先删除相关模型"
        vendor.is_active = False
        vendor.deleted_at = now()
        await db.flush()
        return True, ""


# ========== 分类服务（model_categories）==========

class CategoryService:
    """模型能力分类服务"""

    @staticmethod
    async def list_all(db: AsyncSession) -> List[ModelCategory]:
        """获取所有启用的分类，按 sort_order 排序"""
        return await CategoryRepository.list_all(db)

    @staticmethod
    async def get_by_key(db: AsyncSession, key: str) -> Optional[ModelCategory]:
        """根据分类键（如 reasoning / coding）获取分类"""
        return await CategoryRepository.get_by_key(db, key)

    @staticmethod
    async def get_by_id(db: AsyncSession, category_id: int) -> Optional[ModelCategory]:
        """根据 ID 获取分类"""
        return await CategoryRepository.get_by_id(db, category_id)


# ========== 模型服务（models）==========

class ModelService:
    """AI 模型服务"""

    @staticmethod
    async def list_all(
        db: AsyncSession,
        category_key: Optional[str] = None,
        vendor_slugs: Optional[List[str]] = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Model], int]:
        """
        获取模型列表，支持三个维度筛选（AND 逻辑）：
          - category_key：分类键筛选（如 reasoning / coding）
          - vendor_slugs：研发商 slug 多选（OR 同维度）
          - q：关键词匹配 name / slug / description
        排序规则：mcm.sort_order ASC → m.sort_order ASC → m.name ASC
        """
        return await ModelRepository.list_all(
            db,
            category_key=category_key,
            vendor_slugs=vendor_slugs,
            q=q,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Model]:
        """根据 slug 获取模型（含研发商、分类、报价关联，使用 selectin 预加载）"""
        return await ModelRepository.get_by_slug(db, slug)

    @staticmethod
    async def get_by_id(db: AsyncSession, model_id: int) -> Optional[Model]:
        """根据 ID 获取模型"""
        return await ModelRepository.get_by_id(db, model_id)

    @staticmethod
    async def get_category_briefs(db: AsyncSession, model_id: int) -> List[ModelCategoryBrief]:
        """
        获取模型所属分类列表（含该分类下的排序权重）
        返回的 sort_order 来自 model_category_map，而非 model_categories
        """
        return await ModelRepository.get_category_briefs(db, model_id)

    @staticmethod
    async def create(db: AsyncSession, data) -> Model:
        """
        创建模型。
        - 若 slug 对应活跃记录 → 抛 ValueError（409）
        - 若 slug 对应软删除记录（is_active=False）→ 复用该记录并更新字段
        - 否则 → 创建新记录
        同时写入 ModelCategoryMap 分类关联。
        """
        existing = await ModelRepository.get_by_slug(db, data.slug)
        if existing:
            if existing.is_active:
                raise ValueError(f"slug '{data.slug}' 已存在")
            # 恢复软删除记录
            existing.vendor_id = data.vendor_id
            existing.name = data.name
            existing.description = data.description
            existing.capability_tags = data.capability_tags
            existing.context_window = data.context_window
            existing.max_output_tokens = data.max_output_tokens
            existing.is_reasoning_model = data.is_reasoning_model
            existing.sort_order = data.sort_order
            existing.is_active = data.is_active
            existing.deleted_at = None
            await db.flush()
            # 重建分类关联
            await ModelRepository.delete_category_maps(db, existing.id)
            for cat in data.categories:
                db.add(ModelCategoryMap(model_id=existing.id, category_id=cat.category_id, sort_order=cat.sort_order))
            await db.flush()
            await db.refresh(existing)
            return existing
        # 全新记录
        model = Model(
            vendor_id=data.vendor_id,
            slug=data.slug,
            name=data.name,
            description=data.description,
            capability_tags=data.capability_tags,
            context_window=data.context_window,
            max_output_tokens=data.max_output_tokens,
            is_reasoning_model=data.is_reasoning_model,
            sort_order=data.sort_order,
            is_active=data.is_active,
        )
        db.add(model)
        await db.flush()
        for cat in data.categories:
            db.add(ModelCategoryMap(model_id=model.id, category_id=cat.category_id, sort_order=cat.sort_order))
        await db.flush()
        await db.refresh(model)
        return model

    @staticmethod
    async def update(db: AsyncSession, slug: str, data) -> Optional[Model]:
        """
        更新模型字段。
        若 data.categories 不为 None，则先删除旧分类关联再写入新关联。
        """
        model = await ModelRepository.get_by_slug(db, slug)
        if not model:
            return None
        simple_fields = [
            "name", "description", "capability_tags", "context_window",
            "max_output_tokens", "is_reasoning_model",
            "sort_order", "is_active",
        ]
        for field in simple_fields:
            value = getattr(data, field, None)
            if value is not None:
                setattr(model, field, value)
        await db.flush()
        if data.categories is not None:
            await ModelRepository.delete_category_maps(db, model.id)
            for cat in data.categories:
                db.add(ModelCategoryMap(model_id=model.id, category_id=cat.category_id, sort_order=cat.sort_order))
            await db.flush()
        await db.refresh(model)
        return model

    @staticmethod
    async def delete(db: AsyncSession, slug: str) -> tuple[bool, str]:
        """软删除模型（设置 is_active=False）"""
        model = await ModelRepository.get_by_slug(db, slug)
        if not model:
            return False, "not_found"
        model.is_active = False
        model.deleted_at = now()
        await db.flush()
        return True, ""


# ========== 服务提供商服务（providers）==========

class ProviderService:
    """API 服务提供商服务（≠ 研发商）"""

    @staticmethod
    async def list_all(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[List[Provider], int]:
        """获取所有服务提供商（含已停用），管理端展示；活跃记录排在前面，支持分页"""
        return await ProviderRepository.list_all(db, page=page, page_size=page_size)

    @staticmethod
    async def get_by_id(db: AsyncSession, provider_id: int) -> Optional[Provider]:
        """根据 ID 获取提供商"""
        return await ProviderRepository.get_by_id(db, provider_id)

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Provider]:
        """根据 slug 获取提供商"""
        return await ProviderRepository.get_by_slug(db, slug)

    @staticmethod
    async def create(db: AsyncSession, data) -> Provider:
        """
        创建新服务提供商。
        - 若 slug 对应活跃记录 → 抛 ValueError（409）
        - 若 slug 对应软删除记录（is_active=False）→ 复用该记录并更新字段（恢复）
        - 否则 → 创建新记录
        """
        existing = await ProviderRepository.get_any_by_slug(db, data.slug)
        if existing:
            if existing.is_active:
                raise ValueError(f"slug '{data.slug}' 已存在")
            # 恢复软删除的记录，更新为新提交的数据
            existing.name = data.name
            existing.logo_url = data.logo_url
            existing.is_active = data.is_active
            existing.deleted_at = None
            await db.flush()
            await db.refresh(existing)
            return existing
        provider = Provider(
            slug=data.slug,
            name=data.name,
            logo_url=data.logo_url,
            is_active=data.is_active,
        )
        provider.probe_api_base_url = _normalize_optional_text(getattr(data, "probe_api_base_url", None))
        _update_provider_probe_key(provider, getattr(data, "probe_api_key", None))
        db.add(provider)
        await db.flush()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def update(db: AsyncSession, provider_id: int, data) -> Optional[Provider]:
        """更新服务提供商，仅更新非 None 字段"""
        provider = await ProviderRepository.get_any_by_id(db, provider_id)
        if not provider:
            return None
        payload = data.model_dump(exclude_unset=True)
        probe_api_base_url_supplied = "probe_api_base_url" in data.model_fields_set
        probe_api_key_supplied = "probe_api_key" in data.model_fields_set
        probe_api_base_url = payload.pop("probe_api_base_url", None)
        probe_api_key = payload.pop("probe_api_key", None)

        for field, value in payload.items():
            setattr(provider, field, value)
        if probe_api_base_url_supplied:
            provider.probe_api_base_url = _normalize_optional_text(probe_api_base_url)
        if probe_api_key_supplied:
            _update_provider_probe_key(provider, probe_api_key)
        await db.flush()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def delete(db: AsyncSession, provider_id: int) -> tuple[bool, str]:
        """
        软删除服务提供商（设置 is_active=False）。
        若存在关联 ModelProviderOffering 则拒绝，防止探针任务访问已停用提供商。
        返回 (True, "") 表示成功，(False, 原因) 表示失败。
        """
        provider = await ProviderRepository.get_any_by_id(db, provider_id)
        if not provider:
            return False, "not_found"
        offering_count = await ProviderRepository.count_active_offerings(db, provider_id)
        if offering_count > 0:
            return False, f"该供应商下存在 {offering_count} 条模型报价，请先删除相关报价"
        # 软删除：设置 is_active=False，不物理删除行
        provider.is_active = False
        provider.deleted_at = now()
        await db.flush()
        return True, ""

# ========== 报价服务（model_provider_offerings）==========

class OfferingService:
    """模型-提供商报价服务"""

    @staticmethod
    async def get_active_provider_counts(
        db: AsyncSession,
        model_ids: list[int],
    ) -> dict[int, int]:
        """Return active provider-offering counts keyed by model id."""
        return await OfferingRepository.get_active_provider_counts(db, model_ids)

    @staticmethod
    async def get_by_id(db: AsyncSession, offering_id: int) -> Optional[ModelProviderOffering]:
        """获取单个报价配置"""
        return await OfferingRepository.get_by_id(db, offering_id)

    @staticmethod
    async def list_by_model(db: AsyncSession, model_id: int) -> List[ModelProviderOffering]:
        """获取模型的所有启用报价配置"""
        return await OfferingRepository.list_by_model(db, model_id)

    @staticmethod
    async def list_all_active(db: AsyncSession) -> List[ModelProviderOffering]:
        """获取所有启用的报价配置（供定时任务使用）"""
        return await OfferingRepository.list_all_active(db)

    @staticmethod
    async def list_all_by_model(db: AsyncSession, model_id: int) -> List[ModelProviderOffering]:
        """获取模型的全部报价配置（含已废弃），供管理端展示"""
        return await OfferingRepository.list_all_by_model(db, model_id)

    @staticmethod
    async def create(db: AsyncSession, model_id: int, data) -> ModelProviderOffering:
        """
        创建模型-服务商报价配置。
        - 若同一 (model_id, provider_id) 的活跃记录已存在 → 抛 ValueError（409）
        - 若同一 (model_id, provider_id) 的软删除记录存在 → 复用并恢复
        - 否则 → 创建新记录
        """
        existing = await OfferingRepository.get_any_by_model_provider(
            db,
            model_id,
            data.provider_id,
        )
        if existing:
            if existing.is_active:
                raise ValueError("该服务商的报价配置已存在")
            # 恢复软删除记录，更新价格和配置
            existing.price_input_per_m = data.price_input_per_m
            existing.price_output_per_m = data.price_output_per_m
            existing.provider_model_name = data.provider_model_id
            existing.is_active = True
            existing.deleted_at = None
            await db.flush()
            await db.refresh(existing)
            return existing
        offering = ModelProviderOffering(
            model_id=model_id,
            provider_id=data.provider_id,
            price_input_per_m=data.price_input_per_m,
            price_output_per_m=data.price_output_per_m,
            provider_model_name=data.provider_model_id,
            is_active=True,
        )
        db.add(offering)
        await db.flush()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def delete(db: AsyncSession, offering_id: int) -> bool:
        """软删除报价配置（设置 is_active=False），返回是否找到记录"""
        offering = await OfferingRepository.get_by_id(db, offering_id)
        if not offering:
            return False
        offering.is_active = False
        offering.deleted_at = now()
        await db.flush()
        return True

    @staticmethod
    async def get_metrics(
        db: AsyncSession,
        offering_id: int,
        n: int = 5,
        region: Optional[str] = None,
    ) -> List[OfferingMetricsResponse]:
        """
        获取某个报价的近 N 次成功探测的聚合性能指标
        数据来源：provider_metrics_ranked 视图（WHERE rn <= n）
        支持按 probe_region 筛选；若不传 region 则返回所有区域的聚合结果
        """
        return await OfferingRepository.get_metrics(db, offering_id, n=n, region=region)


# ========== 性能探测记录服务（provider_performance_metrics，append-only）==========

class PerformanceMetricService:
    """性能探测记录服务（只写不改，由定时任务调用）"""

    @staticmethod
    async def record(
        db: AsyncSession,
        offering_id: int,
        success: bool,
        measured_at=None,
        throughput_tps: Optional[float] = None,
        ttft_ms: Optional[int] = None,
        e2e_latency_ms: Optional[int] = None,
        error_code: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        probe_region: Optional[str] = None,
    ) -> ProviderPerformanceMetric:
        """写入一条探测记录（append-only，不 UPDATE）"""
        metric = ProviderPerformanceMetric(
            offering_id=offering_id,
            throughput_tps=throughput_tps,
            ttft_ms=ttft_ms,
            e2e_latency_ms=e2e_latency_ms,
            success=success,
            error_code=error_code,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            probe_region=probe_region,
            measured_at=measured_at or now(),
        )
        db.add(metric)
        await db.flush()
        return metric

    @staticmethod
    async def get_latest_by_offering(
        db: AsyncSession,
        offering_id: int,
    ) -> Optional[ProviderPerformanceMetric]:
        """Return the newest probe row for one offering."""
        return await OfferingRepository.get_latest_metric_by_offering(db, offering_id)

    @staticmethod
    async def get_trend_data(
        db: AsyncSession,
        model_id: int,
        days: int = 7,
        region: Optional[str] = None,
    ) -> list[dict]:
        """Return benchmark trend rows for one model using a calendar-day cutoff."""
        return await OfferingRepository.get_trend_data(db, model_id, days=days, region=region)
