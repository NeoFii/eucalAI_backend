# -*- coding: utf-8 -*-
"""
Testing 服务业务逻辑层
提供模型、研发商、服务提供商、报价和性能指标的查询与写入服务
"""

from typing import List, Optional, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now

from testing.models import (
    ModelCategory,
    ModelVendor,
    Model,
    ModelCategoryMap,
    Provider,
    ModelProviderOffering,
    ProviderPerformanceMetric,
    ProviderMetricsRanked,
)
from testing.schemas import (
    ModelCategoryBrief,
    OfferingMetricsResponse,
)


# ========== 研发商服务（model_vendors）==========

class VendorService:
    """研发商服务（创造模型的公司，≠ 服务提供商）"""

    @staticmethod
    async def list_all(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[List[ModelVendor], int]:
        """获取所有研发商（管理端展示，不过滤 is_active），按名称排序，支持分页"""
        base_query = select(ModelVendor).order_by(ModelVendor.name)
        total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0
        items = list((await db.execute(base_query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[ModelVendor]:
        """根据 slug 获取研发商"""
        result = await db.execute(
            select(ModelVendor).where(ModelVendor.slug == slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, vendor_id: int) -> Optional[ModelVendor]:
        """根据 ID 获取研发商"""
        result = await db.execute(
            select(ModelVendor).where(ModelVendor.id == vendor_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data) -> ModelVendor:
        """
        创建研发商。
        - 若 slug 对应活跃记录 → 抛 ValueError（409）
        - 若 slug 对应软删除记录（is_active=False）→ 复用并更新字段
        - 否则 → 创建新记录
        """
        existing_result = await db.execute(
            select(ModelVendor).where(ModelVendor.slug == data.slug)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            if existing.is_active:
                raise ValueError(f"slug '{data.slug}' 已存在")
            existing.name = data.name
            existing.logo_url = data.logo_url
            existing.is_active = data.is_active
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
        result = await db.execute(
            select(ModelVendor).where(ModelVendor.id == vendor_id)
        )
        vendor = result.scalar_one_or_none()
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
        result = await db.execute(
            select(ModelVendor).where(ModelVendor.id == vendor_id)
        )
        vendor = result.scalar_one_or_none()
        if not vendor:
            return False, "not_found"
        count_result = await db.execute(
            select(func.count()).select_from(Model).where(Model.vendor_id == vendor_id)
        )
        model_count = count_result.scalar() or 0
        if model_count > 0:
            return False, f"该研发商下存在 {model_count} 个模型，请先删除相关模型"
        vendor.is_active = False
        await db.flush()
        return True, ""


# ========== 分类服务（model_categories）==========

class CategoryService:
    """模型能力分类服务"""

    @staticmethod
    async def list_all(db: AsyncSession) -> List[ModelCategory]:
        """获取所有启用的分类，按 sort_order 排序"""
        result = await db.execute(
            select(ModelCategory)
            .where(ModelCategory.is_active == True)
            .order_by(ModelCategory.sort_order, ModelCategory.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_key(db: AsyncSession, key: str) -> Optional[ModelCategory]:
        """根据分类键（如 reasoning / coding）获取分类"""
        result = await db.execute(
            select(ModelCategory).where(ModelCategory.key == key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, category_id: int) -> Optional[ModelCategory]:
        """根据 ID 获取分类"""
        result = await db.execute(
            select(ModelCategory).where(ModelCategory.id == category_id)
        )
        return result.scalar_one_or_none()


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
        query = (
            select(Model)
            .join(ModelVendor, Model.vendor_id == ModelVendor.id)
            .where(Model.is_active == True)
        )

        # 按分类筛选：JOIN model_category_map + model_categories
        if category_key:
            query = (
                query
                .join(ModelCategoryMap, ModelCategoryMap.model_id == Model.id)
                .join(ModelCategory, ModelCategoryMap.category_id == ModelCategory.id)
                .where(ModelCategory.key == category_key)
                # 分类内排序：先按 model_category_map.sort_order，再按模型全局 sort_order
                .order_by(ModelCategoryMap.sort_order, Model.sort_order, Model.name)
            )
        else:
            query = query.order_by(Model.sort_order, Model.name)

        # 按研发商 slug 多选筛选（OR 同维度）
        if vendor_slugs:
            query = query.where(ModelVendor.slug.in_(vendor_slugs))

        # 关键词搜索：模糊匹配 name / slug / description
        if q:
            like_pattern = f"%{q}%"
            query = query.where(
                or_(
                    Model.name.ilike(like_pattern),
                    Model.slug.ilike(like_pattern),
                    Model.description.ilike(like_pattern),
                )
            )

        # 计数（使用子查询避免 count 与 order_by 冲突）
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # 分页
        query = query.offset((page - 1) * page_size).limit(page_size)
        models = list((await db.execute(query)).scalars().all())

        return models, total

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Model]:
        """根据 slug 获取模型（含研发商、分类、报价关联，使用 selectin 预加载）"""
        result = await db.execute(
            select(Model).where(Model.slug == slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, model_id: int) -> Optional[Model]:
        """根据 ID 获取模型"""
        result = await db.execute(
            select(Model).where(Model.id == model_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_category_briefs(db: AsyncSession, model_id: int) -> List[ModelCategoryBrief]:
        """
        获取模型所属分类列表（含该分类下的排序权重）
        返回的 sort_order 来自 model_category_map，而非 model_categories
        """
        rows = await db.execute(
            select(
                ModelCategory.key,
                ModelCategory.name,
                ModelCategoryMap.sort_order,
            )
            .join(ModelCategoryMap, ModelCategoryMap.category_id == ModelCategory.id)
            .where(ModelCategoryMap.model_id == model_id)
            .where(ModelCategory.is_active == True)
            .order_by(ModelCategoryMap.sort_order)
        )
        return [
            ModelCategoryBrief(key=row.key, name=row.name, sort_order=row.sort_order)
            for row in rows.all()
        ]

    @staticmethod
    async def create(db: AsyncSession, data) -> Model:
        """
        创建模型。
        - 若 slug 对应活跃记录 → 抛 ValueError（409）
        - 若 slug 对应软删除记录（is_active=False）→ 复用该记录并更新字段
        - 否则 → 创建新记录
        同时写入 ModelCategoryMap 分类关联。
        """
        existing_result = await db.execute(
            select(Model).where(Model.slug == data.slug)
        )
        existing = existing_result.scalar_one_or_none()
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
            existing.knowledge_cutoff = data.knowledge_cutoff
            existing.is_reasoning_model = data.is_reasoning_model
            existing.sort_order = data.sort_order
            existing.is_active = data.is_active
            await db.flush()
            # 重建分类关联
            await db.execute(
                ModelCategoryMap.__table__.delete().where(ModelCategoryMap.model_id == existing.id)
            )
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
            knowledge_cutoff=data.knowledge_cutoff,
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
        result = await db.execute(select(Model).where(Model.slug == slug))
        model = result.scalar_one_or_none()
        if not model:
            return None
        simple_fields = [
            "name", "description", "capability_tags", "context_window",
            "max_output_tokens", "knowledge_cutoff", "is_reasoning_model",
            "sort_order", "is_active",
        ]
        for field in simple_fields:
            value = getattr(data, field, None)
            if value is not None:
                setattr(model, field, value)
        await db.flush()
        if data.categories is not None:
            await db.execute(
                ModelCategoryMap.__table__.delete().where(ModelCategoryMap.model_id == model.id)
            )
            for cat in data.categories:
                db.add(ModelCategoryMap(model_id=model.id, category_id=cat.category_id, sort_order=cat.sort_order))
            await db.flush()
        await db.refresh(model)
        return model

    @staticmethod
    async def delete(db: AsyncSession, slug: str) -> tuple[bool, str]:
        """软删除模型（设置 is_active=False）"""
        result = await db.execute(select(Model).where(Model.slug == slug))
        model = result.scalar_one_or_none()
        if not model:
            return False, "not_found"
        model.is_active = False
        await db.flush()
        return True, ""


# ========== 服务提供商服务（providers）==========

class ProviderService:
    """API 服务提供商服务（≠ 研发商）"""

    @staticmethod
    async def list_all(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[List[Provider], int]:
        """获取所有服务提供商（含已停用），管理端展示；活跃记录排在前面，支持分页"""
        base_query = select(Provider).order_by(Provider.is_active.desc(), Provider.name)
        total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0
        items = list((await db.execute(base_query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    @staticmethod
    async def get_by_id(db: AsyncSession, provider_id: int) -> Optional[Provider]:
        """根据 ID 获取提供商"""
        result = await db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Provider]:
        """根据 slug 获取提供商"""
        result = await db.execute(
            select(Provider).where(Provider.slug == slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data) -> Provider:
        """
        创建新服务提供商。
        - 若 slug 对应活跃记录 → 抛 ValueError（409）
        - 若 slug 对应软删除记录（is_active=False）→ 复用该记录并更新字段（恢复）
        - 否则 → 创建新记录
        """
        existing_result = await db.execute(
            select(Provider).where(Provider.slug == data.slug)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            if existing.is_active:
                raise ValueError(f"slug '{data.slug}' 已存在")
            # 恢复软删除的记录，更新为新提交的数据
            existing.name = data.name
            existing.logo_url = data.logo_url
            existing.is_active = data.is_active
            await db.flush()
            await db.refresh(existing)
            return existing
        provider = Provider(
            slug=data.slug,
            name=data.name,
            logo_url=data.logo_url,
            is_active=data.is_active,
        )
        db.add(provider)
        await db.flush()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def update(db: AsyncSession, provider_id: int, data) -> Optional[Provider]:
        """更新服务提供商，仅更新非 None 字段"""
        result = await db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(provider, field, value)
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
        result = await db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            return False, "not_found"
        count_result = await db.execute(
            select(func.count()).select_from(ModelProviderOffering).where(
                ModelProviderOffering.provider_id == provider_id
            )
        )
        offering_count = count_result.scalar() or 0
        if offering_count > 0:
            return False, f"该供应商下存在 {offering_count} 条模型报价，请先删除相关报价"
        # 软删除：设置 is_active=False，不物理删除行
        provider.is_active = False
        await db.flush()
        return True, ""

# ========== 报价服务（model_provider_offerings）==========

class OfferingService:
    """模型-提供商报价服务"""

    @staticmethod
    async def list_by_model(db: AsyncSession, model_id: int) -> List[ModelProviderOffering]:
        """获取模型的所有启用报价配置"""
        result = await db.execute(
            select(ModelProviderOffering)
            .where(
                and_(
                    ModelProviderOffering.model_id == model_id,
                    ModelProviderOffering.is_active == True,
                )
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all_active(db: AsyncSession) -> List[ModelProviderOffering]:
        """获取所有启用的报价配置（供定时任务使用）"""
        result = await db.execute(
            select(ModelProviderOffering).where(ModelProviderOffering.is_active == True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all_by_model(db: AsyncSession, model_id: int) -> List[ModelProviderOffering]:
        """获取模型的全部报价配置（含已废弃），供管理端展示"""
        result = await db.execute(
            select(ModelProviderOffering)
            .where(ModelProviderOffering.model_id == model_id)
            .order_by(ModelProviderOffering.is_active.desc(), ModelProviderOffering.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, model_id: int, data) -> ModelProviderOffering:
        """
        创建模型-服务商报价配置。
        - 若同一 (model_id, provider_id) 的活跃记录已存在 → 抛 ValueError（409）
        - 若同一 (model_id, provider_id) 的软删除记录存在 → 复用并恢复
        - 否则 → 创建新记录
        """
        existing_result = await db.execute(
            select(ModelProviderOffering).where(
                and_(
                    ModelProviderOffering.model_id == model_id,
                    ModelProviderOffering.provider_id == data.provider_id,
                )
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            if existing.is_active:
                raise ValueError("该服务商的报价配置已存在")
            # 恢复软删除记录，更新价格和配置
            existing.price_input_per_m = data.price_input_per_m
            existing.price_output_per_m = data.price_output_per_m
            existing.provider_model_id = data.provider_model_id
            existing.is_active = True
            await db.flush()
            await db.refresh(existing)
            return existing
        offering = ModelProviderOffering(
            model_id=model_id,
            provider_id=data.provider_id,
            price_input_per_m=data.price_input_per_m,
            price_output_per_m=data.price_output_per_m,
            provider_model_id=data.provider_model_id,
            is_active=True,
        )
        db.add(offering)
        await db.flush()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def delete(db: AsyncSession, offering_id: int) -> bool:
        """软删除报价配置（设置 is_active=False），返回是否找到记录"""
        result = await db.execute(
            select(ModelProviderOffering).where(ModelProviderOffering.id == offering_id)
        )
        offering = result.scalar_one_or_none()
        if not offering:
            return False
        offering.is_active = False
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
        stmt = (
            select(
                ProviderMetricsRanked.probe_region,
                func.round(func.avg(ProviderMetricsRanked.throughput_tps), 2).label("avg_throughput_tps"),
                func.round(func.avg(ProviderMetricsRanked.ttft_ms), 0).label("avg_ttft_ms"),
                func.round(func.avg(ProviderMetricsRanked.e2e_latency_ms), 0).label("avg_e2e_latency_ms"),
                func.count().label("sample_count"),
                func.max(ProviderMetricsRanked.measured_at).label("last_measured_at"),
            )
            .where(ProviderMetricsRanked.offering_id == offering_id)
            .where(ProviderMetricsRanked.rn <= n)
            .group_by(ProviderMetricsRanked.probe_region)
        )
        if region:
            stmt = stmt.where(ProviderMetricsRanked.probe_region == region)

        rows = (await db.execute(stmt)).all()
        return [
            OfferingMetricsResponse(
                probe_region=row.probe_region,
                avg_throughput_tps=float(row.avg_throughput_tps) if row.avg_throughput_tps else None,
                avg_ttft_ms=int(row.avg_ttft_ms) if row.avg_ttft_ms else None,
                avg_e2e_latency_ms=int(row.avg_e2e_latency_ms) if row.avg_e2e_latency_ms else None,
                sample_count=row.sample_count,
                last_measured_at=row.last_measured_at,
            )
            for row in rows
        ]


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
