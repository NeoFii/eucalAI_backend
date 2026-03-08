# -*- coding: utf-8 -*-
"""
Testing 服务业务逻辑层
"""

from typing import List, Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from testing.models import (
    ModelCategory,
    ModelCategoryMapping,
    Model,
    ModelTag,
    Provider,
    ModelProvider,
    BenchmarkResult,
)


# ========== 分类服务 ==========

class CategoryService:
    """分类服务"""

    @staticmethod
    async def create(
        db: AsyncSession,
        name_zh: str,
        name_en: str,
        slug: str,
        description_zh: Optional[str] = None,
        description_en: Optional[str] = None,
        icon: Optional[str] = None,
        sort_order: int = 0,
    ) -> ModelCategory:
        """创建分类"""
        category = ModelCategory(
            name_zh=name_zh,
            name_en=name_en,
            slug=slug,
            description_zh=description_zh,
            description_en=description_en,
            icon=icon,
            sort_order=sort_order,
        )
        db.add(category)
        await db.flush()
        return category

    @staticmethod
    async def get_by_id(db: AsyncSession, category_id: int) -> Optional[ModelCategory]:
        """根据ID获取分类"""
        result = await db.execute(
            select(ModelCategory).where(ModelCategory.id == category_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[ModelCategory]:
        """根据slug获取分类"""
        result = await db.execute(
            select(ModelCategory).where(ModelCategory.slug == slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession) -> List[ModelCategory]:
        """获取所有分类"""
        result = await db.execute(
            select(ModelCategory).order_by(ModelCategory.sort_order, ModelCategory.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def update(
        db: AsyncSession,
        category_id: int,
        **kwargs,
    ) -> Optional[ModelCategory]:
        """更新分类"""
        category = await CategoryService.get_by_id(db, category_id)
        if not category:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(category, key):
                setattr(category, key, value)

        await db.flush()
        return category

    @staticmethod
    async def delete(db: AsyncSession, category_id: int) -> bool:
        """删除分类"""
        category = await CategoryService.get_by_id(db, category_id)
        if not category:
            return False

        await db.delete(category)
        await db.flush()
        return True


# ========== 模型服务 ==========

class ModelService:
    """模型服务"""

    @staticmethod
    async def create(
        db: AsyncSession,
        model_id: str,
        name: str,
        name_zh: Optional[str] = None,
        description_zh: Optional[str] = None,
        description_en: Optional[str] = None,
        context_length: int = 0,
        model_size: Optional[str] = None,
        is_open_source: bool = False,
        is_active: bool = True,
        category_ids: Optional[List[int]] = None,
        tag_names: Optional[List[str]] = None,
    ) -> Model:
        """创建模型"""
        model = Model(
            model_id=model_id,
            name=name,
            name_zh=name_zh,
            description_zh=description_zh,
            description_en=description_en,
            context_length=context_length,
            model_size=model_size,
            is_open_source=is_open_source,
            is_active=is_active,
        )
        db.add(model)
        await db.flush()

        # 添加分类关联
        if category_ids:
            for idx, cat_id in enumerate(category_ids):
                mapping = ModelCategoryMapping(
                    model_id=model.id,
                    category_id=cat_id,
                    is_primary=(idx == 0),
                )
                db.add(mapping)

        # 添加标签
        if tag_names:
            for tag_name in tag_names:
                tag = ModelTag(model_id=model.id, tag=tag_name)
                db.add(tag)

        await db.flush()
        return model

    @staticmethod
    async def get_by_id(db: AsyncSession, model_id: int) -> Optional[Model]:
        """根据ID获取模型"""
        result = await db.execute(
            select(Model).where(Model.id == model_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_model_id(db: AsyncSession, model_id: str) -> Optional[Model]:
        """根据model_id获取模型"""
        result = await db.execute(
            select(Model).where(Model.model_id == model_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        category_slug: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Model], int]:
        """获取模型列表"""
        query = select(Model).where(Model.is_active == True)

        # 按分类筛选
        if category_slug:
            query = query.join(ModelCategoryMapping).join(ModelCategory).where(
                ModelCategory.slug == category_slug
            )

        # 计数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(Model.id).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        models = list(result.scalars().all())

        return models, total

    @staticmethod
    async def list_by_category(
        db: AsyncSession,
        category_slug: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Model], int]:
        """获取指定分类下的模型"""
        return await ModelService.list_all(db, category_slug, page, page_size)

    @staticmethod
    async def get_tags(db: AsyncSession, model_id: int) -> List[str]:
        """获取模型的标签列表"""
        result = await db.execute(
            select(ModelTag.tag).where(ModelTag.model_id == model_id)
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def get_categories_info(db: AsyncSession, model_id: int) -> List[dict]:
        """获取模型的分类信息"""
        result = await db.execute(
            select(ModelCategory).join(ModelCategoryMapping).where(
                ModelCategoryMapping.model_id == model_id
            )
        )
        categories = result.scalars().all()
        return [
            {"slug": c.slug, "name_zh": c.name_zh}
            for c in categories
        ]

    @staticmethod
    async def get_provider_count(db: AsyncSession, model_id: int) -> int:
        """获取模型的供应商数量"""
        result = await db.execute(
            select(func.count()).select_from(ModelProvider).where(
                and_(
                    ModelProvider.model_id == model_id,
                    ModelProvider.is_active == True
                )
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def update(
        db: AsyncSession,
        model_id: int,
        **kwargs,
    ) -> Optional[Model]:
        """更新模型"""
        model = await ModelService.get_by_id(db, model_id)
        if not model:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(model, key):
                setattr(model, key, value)

        await db.flush()
        return model


# ========== 供应商服务 ==========

class ProviderService:
    """供应商服务"""

    @staticmethod
    async def create(
        db: AsyncSession,
        provider_id: str,
        name: str,
        name_zh: Optional[str] = None,
        logo_url: Optional[str] = None,
        color: Optional[str] = None,
        is_active: bool = True,
        sort_order: int = 0,
    ) -> Provider:
        """创建供应商"""
        provider = Provider(
            provider_id=provider_id,
            name=name,
            name_zh=name_zh,
            logo_url=logo_url,
            color=color,
            is_active=is_active,
            sort_order=sort_order,
        )
        db.add(provider)
        await db.flush()
        return provider

    @staticmethod
    async def get_by_id(db: AsyncSession, provider_id: int) -> Optional[Provider]:
        """根据ID获取供应商"""
        result = await db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_provider_id(db: AsyncSession, provider_id: str) -> Optional[Provider]:
        """根据provider_id获取供应商"""
        result = await db.execute(
            select(Provider).where(Provider.provider_id == provider_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession) -> List[Provider]:
        """获取所有供应商"""
        result = await db.execute(
            select(Provider).where(Provider.is_active == True).order_by(Provider.sort_order, Provider.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_model_count(db: AsyncSession, provider_id: int) -> int:
        """获取供应商的模型数量"""
        result = await db.execute(
            select(func.count()).select_from(ModelProvider).where(
                and_(
                    ModelProvider.provider_id == provider_id,
                    ModelProvider.is_active == True
                )
            )
        )
        return result.scalar() or 0


# ========== 模型供应商关联服务 ==========

class ModelProviderService:
    """模型供应商关联服务"""

    @staticmethod
    async def create(
        db: AsyncSession,
        model_id: int,
        provider_id: int,
        api_model_name: str,
        routing_alias: Optional[str] = None,
        input_price_cny_1m: Optional[float] = None,
        output_price_cny_1m: Optional[float] = None,
        rate_limit_rpm: int = 60,
        is_default: bool = False,
        is_active: bool = True,
    ) -> ModelProvider:
        """创建模型供应商关联"""
        mp = ModelProvider(
            model_id=model_id,
            provider_id=provider_id,
            api_model_name=api_model_name,
            routing_alias=routing_alias,
            input_price_cny_1m=input_price_cny_1m,
            output_price_cny_1m=output_price_cny_1m,
            rate_limit_rpm=rate_limit_rpm,
            is_default=is_default,
            is_active=is_active,
        )
        db.add(mp)
        await db.flush()
        return mp

    @staticmethod
    async def get_by_id(db: AsyncSession, mp_id: int) -> Optional[ModelProvider]:
        """根据ID获取"""
        result = await db.execute(
            select(ModelProvider).where(ModelProvider.id == mp_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_model(db: AsyncSession, model_id: int) -> List[ModelProvider]:
        """获取模型的所有供应商关联"""
        result = await db.execute(
            select(ModelProvider).where(
                and_(
                    ModelProvider.model_id == model_id,
                    ModelProvider.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_provider(db: AsyncSession, provider_id: int) -> List[ModelProvider]:
        """获取供应商的所有模型关联"""
        result = await db.execute(
            select(ModelProvider).where(
                and_(
                    ModelProvider.provider_id == provider_id,
                    ModelProvider.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active(db: AsyncSession) -> List[ModelProvider]:
        """获取所有活跃的模型供应商关联"""
        result = await db.execute(
            select(ModelProvider).where(ModelProvider.is_active == True)
        )
        return list(result.scalars().all())


# ========== 性能测试服务 ==========

class BenchmarkService:
    """性能测试服务"""

    @staticmethod
    async def create_result(
        db: AsyncSession,
        model_provider_id: int,
        latency_ttft: Optional[float] = None,
        latency_total: Optional[float] = None,
        throughput: Optional[float] = None,
        success_count: int = 1,
        fail_count: int = 0,
        test_prompt: Optional[str] = None,
    ) -> BenchmarkResult:
        """创建测试结果"""
        result = BenchmarkResult(
            model_provider_id=model_provider_id,
            latency_ttft=latency_ttft,
            latency_total=latency_total,
            throughput=throughput,
            success_count=success_count,
            fail_count=fail_count,
            test_prompt=test_prompt,
        )
        db.add(result)
        await db.flush()
        return result

    @staticmethod
    async def get_stats(
        db: AsyncSession,
        model_provider_id: int,
        hours: int = 24,
    ) -> dict:
        """获取性能统计数据"""
        from datetime import datetime, timedelta

        # 计算时间范围
        start_time = datetime.utcnow() - timedelta(hours=hours)

        # 查询最近 N 小时内的测试结果
        query = select(
            func.avg(BenchmarkResult.latency_ttft).label("avg_ttft"),
            func.avg(BenchmarkResult.latency_total).label("avg_total"),
            func.avg(BenchmarkResult.throughput).label("avg_throughput"),
            func.sum(BenchmarkResult.success_count).label("total_success"),
            func.sum(BenchmarkResult.fail_count).label("total_fail"),
            func.count(BenchmarkResult.id).label("test_count"),
            func.max(BenchmarkResult.test_at).label("last_test_at"),
        ).where(
            and_(
                BenchmarkResult.model_provider_id == model_provider_id,
                BenchmarkResult.test_at >= start_time,
            )
        )

        result = await db.execute(query)
        row = result.one()

        total_success = row.total_success or 0
        total_fail = row.total_fail or 0
        total_tests = total_success + total_fail

        return {
            "model_provider_id": model_provider_id,
            "avg_latency_ttft": float(row.avg_ttft) if row.avg_ttft else None,
            "avg_latency_total": float(row.avg_total) if row.avg_total else None,
            "avg_throughput": float(row.avg_throughput) if row.avg_throughput else None,
            "success_rate": (total_success / total_tests * 100) if total_tests > 0 else None,
            "success_count": total_success,
            "fail_count": total_fail,
            "test_count": row.test_count or 0,
            "last_test_at": row.last_test_at,
        }

    @staticmethod
    async def get_provider_stats(
        db: AsyncSession,
        provider_id: int,
    ) -> List[dict]:
        """获取供应商的所有模型性能统计"""
        # 获取该供应商的所有活跃模型关联
        model_providers = await ModelProviderService.list_by_provider(db, provider_id)

        stats_list = []
        for mp in model_providers:
            stats = await BenchmarkService.get_stats(db, mp.id)
            stats_list.append({
                "model_provider_id": mp.id,
                "model_id": mp.model_id,
                "api_model_name": mp.api_model_name,
                "input_price_cny_1m": float(mp.input_price_cny_1m) if mp.input_price_cny_1m else None,
                "output_price_cny_1m": float(mp.output_price_cny_1m) if mp.output_price_cny_1m else None,
                "stats": stats,
            })

        return stats_list

    @staticmethod
    async def cleanup_old_results(db: AsyncSession, days: int = 7, max_per_provider: int = 100) -> int:
        """清理旧的测试结果"""
        from datetime import datetime, timedelta

        # 删除指定天数之前的数据
        cutoff_time = datetime.utcnow() - timedelta(days=days)

        # 获取需要删除的ID
        subquery = (
            select(BenchmarkResult.id)
            .where(BenchmarkResult.test_at < cutoff_time)
        )
        result = await db.execute(subquery)
        ids_to_delete = [row[0] for row in result.all()]

        if ids_to_delete:
            await db.execute(
                BenchmarkResult.__table__.delete().where(BenchmarkResult.id.in_(ids_to_delete))
            )

        return len(ids_to_delete)
