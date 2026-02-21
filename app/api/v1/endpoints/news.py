"""
新闻 API 端点
提供新闻列表、详情等接口
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Path, Query

from app.models.schemas import NewsDetailResponse, NewsItem, NewsListResponse

router = APIRouter()


# 模拟新闻数据（实际项目中应从数据库读取）
MOCK_NEWS = [
    {
        "id": 1,
        "title": "公司荣获2024年度最佳创新企业奖",
        "summary": "凭借卓越的技术创新能力，公司在年度评选中脱颖而出，荣获最佳创新企业称号。",
        "content": "这是一篇详细的新闻内容...",
        "cover_image": "/images/news-1.jpg",
        "author": "编辑部",
        "category": "公司新闻",
        "is_published": True,
        "created_at": datetime(2024, 1, 15),
        "updated_at": datetime(2024, 1, 15),
        "view_count": 1250,
    },
    {
        "id": 2,
        "title": "新产品发布会圆满举行",
        "summary": "公司最新产品线正式发布，吸引了数百位行业专家和合作伙伴参加。",
        "content": "这是一篇详细的新闻内容...",
        "cover_image": "/images/news-2.jpg",
        "author": "市场部",
        "category": "产品动态",
        "is_published": True,
        "created_at": datetime(2024, 2, 20),
        "updated_at": datetime(2024, 2, 21),
        "view_count": 890,
    },
    {
        "id": 3,
        "title": "与知名企业达成战略合作协议",
        "summary": "双方将在技术研发、市场拓展等领域展开深度合作，共同推动行业发展。",
        "content": "这是一篇详细的新闻内容...",
        "cover_image": "/images/news-3.jpg",
        "author": "商务部",
        "category": "合作动态",
        "is_published": True,
        "created_at": datetime(2024, 3, 10),
        "updated_at": None,
        "view_count": 650,
    },
]


@router.get("", response_model=NewsListResponse, summary="获取新闻列表")
async def get_news_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    category: str = Query(None, description="分类筛选"),
) -> NewsListResponse:
    """
    获取新闻列表，支持分页和分类筛选
    """
    # 筛选数据
    filtered_news = MOCK_NEWS
    if category:
        filtered_news = [n for n in filtered_news if n["category"] == category]

    # 只返回已发布的新闻
    filtered_news = [n for n in filtered_news if n["is_published"]]

    # 按时间倒序排列
    filtered_news.sort(key=lambda x: x["created_at"], reverse=True)

    # 分页
    total = len(filtered_news)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = filtered_news[start:end]

    return NewsListResponse(
        data=[NewsItem(**item) for item in page_data],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/categories", summary="获取新闻分类")
async def get_news_categories():
    """
    获取所有新闻分类
    """
    categories = list(set(n["category"] for n in MOCK_NEWS))
    return {"data": categories}


@router.get("/{news_id}", response_model=NewsDetailResponse, summary="获取新闻详情")
async def get_news_detail(
    news_id: int = Path(..., ge=1, description="新闻ID")
) -> NewsDetailResponse:
    """
    根据 ID 获取新闻详情
    """
    news_item = next((n for n in MOCK_NEWS if n["id"] == news_id), None)

    if not news_item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="新闻不存在")

    return NewsDetailResponse(data=NewsItem(**news_item))
