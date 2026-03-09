"""
统一异常处理器注册
提供公共的异常处理器注册函数，消除各服务重复代码
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from common.core.exceptions import APIException


def register_exception_handlers(app: FastAPI) -> None:
    """
    为 FastAPI 应用注册统一的异常处理器

    通过捕获 APIException 基类实现所有自定义异常的统一处理，
    无需为每个异常子类单独注册处理器。
    """

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        """统一处理所有 APIException 及其子类"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.detail,
            },
        )
