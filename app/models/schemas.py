"""
API 数据模型（Pydantic Schemas）
定义请求和响应的数据结构
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ==================== 基础响应 ====================

class BaseResponse(BaseModel):
    """统一响应基类"""
    code: str = "success"
    message: str = "操作成功"


class DataResponse(BaseResponse):
    """带数据的响应"""
    data: dict


class ListResponse(BaseResponse):
    """列表响应"""
    data: List[dict]
    total: int = 0
    page: int = 1
    page_size: int = 10


# ==================== 新闻相关 ====================

class NewsBase(BaseModel):
    """新闻基础模型"""
    title: str = Field(..., min_length=1, max_length=200, description="新闻标题")
    summary: Optional[str] = Field(None, max_length=500, description="新闻摘要")
    content: Optional[str] = Field(None, description="新闻内容（Markdown/HTML）")
    cover_image: Optional[str] = Field(None, description="封面图片 URL")
    author: Optional[str] = Field(None, max_length=50, description="作者")
    category: Optional[str] = Field(None, max_length=50, description="分类")
    is_published: bool = Field(True, description="是否发布")


class NewsCreate(NewsBase):
    """创建新闻请求"""
    pass


class NewsUpdate(BaseModel):
    """更新新闻请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    summary: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    cover_image: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    is_published: Optional[bool] = None


class NewsItem(NewsBase):
    """新闻详情响应"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    view_count: int = 0

    class Config:
        from_attributes = True


class NewsListResponse(BaseResponse):
    """新闻列表响应"""
    data: List[NewsItem]
    total: int


class NewsDetailResponse(BaseResponse):
    """新闻详情响应"""
    data: NewsItem


# ==================== 产品相关 ====================

class ProductBase(BaseModel):
    """产品基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="产品名称")
    short_description: Optional[str] = Field(None, max_length=200, description="简短描述")
    full_description: Optional[str] = Field(None, description="详细描述")
    image: Optional[str] = Field(None, description="产品图片 URL")
    icon: Optional[str] = Field(None, description="产品图标")
    features: Optional[List[str]] = Field(None, description="产品特性列表")
    category: Optional[str] = Field(None, max_length=50, description="产品分类")
    is_active: bool = Field(True, description="是否上架")
    sort_order: int = Field(0, description="排序权重")


class ProductItem(ProductBase):
    """产品详情"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ProductListResponse(BaseResponse):
    """产品列表响应"""
    data: List[ProductItem]


class ProductDetailResponse(BaseResponse):
    """产品详情响应"""
    data: ProductItem


# ==================== 联系表单 ====================

class ContactForm(BaseModel):
    """联系表单请求"""
    name: str = Field(..., min_length=2, max_length=50, description="姓名")
    email: EmailStr = Field(..., description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="电话")
    company: Optional[str] = Field(None, max_length=100, description="公司名称")
    subject: str = Field(..., min_length=1, max_length=200, description="主题")
    message: str = Field(..., min_length=10, max_length=2000, description="留言内容")


class ContactFormResponse(BaseResponse):
    """联系表单提交响应"""
    data: dict = Field(default_factory=dict)


# ==================== 公司信息 ====================

class CompanyInfo(BaseModel):
    """公司信息"""
    name: str = Field(..., description="公司名称")
    slogan: Optional[str] = Field(None, description="公司口号")
    description: Optional[str] = Field(None, description="公司介绍")
    address: Optional[str] = Field(None, description="地址")
    phone: Optional[str] = Field(None, description="电话")
    email: Optional[str] = Field(None, description="邮箱")
    business_hours: Optional[str] = Field(None, description="营业时间")
    social_media: Optional[dict] = Field(None, description="社交媒体链接")
