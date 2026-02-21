"""
产品 API 端点
提供产品列表、详情等接口
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Path, Query

from app.models.schemas import ProductDetailResponse, ProductItem, ProductListResponse

router = APIRouter()


# 模拟产品数据
MOCK_PRODUCTS = [
    {
        "id": 1,
        "name": "企业级云服务平台",
        "short_description": "一站式企业上云解决方案，助力数字化转型",
        "full_description": "我们的企业级云服务平台提供完整的基础设施即服务(IaaS)和平台即服务(PaaS)能力...",
        "image": "/images/product-1.jpg",
        "icon": "Cloud",
        "features": ["弹性扩展", "高可用架构", "安全合规", "7x24技术支持"],
        "category": "云服务",
        "is_active": True,
        "sort_order": 1,
        "created_at": datetime(2024, 1, 1),
    },
    {
        "id": 2,
        "name": "智能数据分析系统",
        "short_description": "AI驱动的数据分析平台，洞察业务价值",
        "full_description": "智能数据分析系统集成了最新的机器学习和深度学习算法...",
        "image": "/images/product-2.jpg",
        "icon": "BarChart",
        "features": ["实时分析", "可视化报表", "预测建模", "多源数据集成"],
        "category": "数据智能",
        "is_active": True,
        "sort_order": 2,
        "created_at": datetime(2024, 2, 1),
    },
    {
        "id": 3,
        "name": "移动应用开发框架",
        "short_description": "跨平台移动应用快速开发解决方案",
        "full_description": "我们的移动应用开发框架支持一次编写，多端运行...",
        "image": "/images/product-3.jpg",
        "icon": "Smartphone",
        "features": ["跨平台支持", "热更新", "原生性能", "丰富组件库"],
        "category": "开发工具",
        "is_active": True,
        "sort_order": 3,
        "created_at": datetime(2024, 3, 1),
    },
    {
        "id": 4,
        "name": "网络安全防护体系",
        "short_description": "全方位网络安全解决方案，守护数字资产",
        "full_description": "网络安全防护体系涵盖边界安全、终端安全、应用安全等多个层面...",
        "image": "/images/product-4.jpg",
        "icon": "Shield",
        "features": ["威胁检测", "入侵防御", "漏洞扫描", "安全审计"],
        "category": "网络安全",
        "is_active": True,
        "sort_order": 4,
        "created_at": datetime(2024, 3, 15),
    },
]


@router.get("", response_model=ProductListResponse, summary="获取产品列表")
async def get_product_list(
    category: str = Query(None, description="分类筛选"),
) -> ProductListResponse:
    """
    获取产品列表，支持按分类筛选
    """
    # 筛选数据
    filtered_products = MOCK_PRODUCTS
    if category:
        filtered_products = [p for p in filtered_products if p["category"] == category]

    # 只返回上架的产品
    filtered_products = [p for p in filtered_products if p["is_active"]]

    # 按排序权重排列
    filtered_products.sort(key=lambda x: x["sort_order"])

    return ProductListResponse(
        data=[ProductItem(**item) for item in filtered_products]
    )


@router.get("/categories", summary="获取产品分类")
async def get_product_categories():
    """
    获取所有产品分类
    """
    categories = list(set(p["category"] for p in MOCK_PRODUCTS))
    return {"data": categories}


@router.get("/{product_id}", response_model=ProductDetailResponse, summary="获取产品详情")
async def get_product_detail(
    product_id: int = Path(..., ge=1, description="产品ID")
) -> ProductDetailResponse:
    """
    根据 ID 获取产品详情
    """
    product_item = next((p for p in MOCK_PRODUCTS if p["id"] == product_id), None)

    if not product_item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="产品不存在")

    return ProductDetailResponse(data=ProductItem(**product_item))
