"""
Pytest 配置文件
提供测试夹具和配置
"""

import asyncio
import os
import sys
from typing import Generator

import pytest
from httpx import AsyncClient, ASGITransport

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.db.database import engine


# 配置 pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """创建事件循环"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    # 关闭前先清理引擎
    try:
        loop.run_until_complete(engine.dispose())
    except Exception:
        pass
    loop.close()


@pytest.fixture(autouse=True)
async def cleanup_db():
    """每个测试后清理数据库连接"""
    yield
    # 尝试清理连接池
    try:
        await engine.dispose()
    except Exception:
        pass
    # 等待异步任务完成
    await asyncio.sleep(0.05)


@pytest.fixture
async def client() -> AsyncClient:
    """
    创建测试客户端
    使用 httpx 的 AsyncClient 直接测试 FastAPI 应用
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(client: AsyncClient) -> dict:
    """
    创建已认证的测试客户端
    返回包含 client 和 tokens 的字典
    """
    # 使用测试邮箱注册
    test_email = "test@example.com"
    test_password = "Test1234!"

    # 先尝试发送验证码
    await client.post(
        "/api/v1/auth/send-code",
        json={"email": test_email, "purpose": "register"}
    )

    # 注意：实际测试中需要真实的邮箱验证码
    # 这里简化处理，返回未认证的客户端
    return {
        "client": client,
        "email": test_email,
        "password": test_password,
        "access_token": None,
        "refresh_token": None,
    }


@pytest.fixture
def test_email() -> str:
    """测试用邮箱"""
    return "test@example.com"


@pytest.fixture
def test_password() -> str:
    """测试用密码"""
    return "Test1234!"


@pytest.fixture
def valid_verification_code() -> str:
    """有效的测试验证码"""
    return "123456"
