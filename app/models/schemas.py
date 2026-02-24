"""
API 数据模型（Pydantic Schemas）
定义请求和响应的数据结构
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 基础响应 ====================

class BaseResponse(BaseModel):
    """统一响应基类"""
    code: str = "success"
    message: str = "操作成功"


class DataResponse(BaseResponse):
    """带数据的响应"""
    data: Dict[str, Any]


class ListResponse(BaseResponse):
    """列表响应"""
    data: List[Any]
    total: int = 0
    page: int = 1
    page_size: int = 10
