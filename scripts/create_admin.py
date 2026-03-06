"""
创建管理员账号脚本
用于创建第一个管理员账号

用法:
    cd backend
    python scripts/create_admin.py
"""

import os
import sys
from pathlib import Path

# 设置环境变量 - 先加载 .env 文件
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)  # 切换到 backend 目录

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# 设置环境变量（作为后备）
os.environ.setdefault("INTERNAL_SECRET", os.getenv("INTERNAL_SECRET", "test_secret"))
os.environ.setdefault("JWT_SECRET_KEY", os.getenv("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!"))

# 添加 backend 到路径
sys.path.insert(0, backend_dir)


def main():
    """创建管理员账号"""
    import asyncio

    from sqlalchemy import select

    from common.db.database import create_engine, init_session_factory, get_db_context
    from common.utils.password import hash_password
    from common.utils.snowflake import configure_snowflake, generate_snowflake_id
    from admin.models.admin_user import AdminUser

    # 配置雪花ID
    configure_snowflake(worker_id=1, datacenter_id=1)

    # 获取管理员信息
    print("=" * 50)
    print("创建管理员账号")
    print("=" * 50)

    email = input("管理员邮箱: ").strip()
    name = input("管理员姓名: ").strip()
    password = input("密码: ").strip()

    if not email or not name or not password:
        print("错误: 所有字段都是必填的")
        sys.exit(1)

    if len(password) < 8:
        print("错误: 密码长度至少8位")
        sys.exit(1)

    # 从配置获取数据库URL
    from admin.config import settings
    database_url = settings.DATABASE_URL

    async def _create_admin():
        # 初始化数据库连接
        create_engine(database_url=database_url)
        init_session_factory()

        async with get_db_context() as db:
            # 检查邮箱是否已存在
            result = await db.execute(
                select(AdminUser).where(AdminUser.email == email)
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"错误: 邮箱 {email} 已存在")
                sys.exit(1)

            # 生成雪花ID
            uid = generate_snowflake_id()

            # 创建管理员
            admin = AdminUser(
                uid=uid,
                email=email,
                name=name,
                password_hash=hash_password(password),
                status=1,
                role="super",  # 第一个管理员为超级管理员
            )

            db.add(admin)
            await db.commit()

            print(f"")
            print("=" * 50)
            print(f"管理员创建成功!")
            print(f"  UID: {uid}")
            print(f"  邮箱: {email}")
            print(f"  姓名: {name}")
            print(f"  角色: 超级管理员")
            print("=" * 50)

    asyncio.run(_create_admin())


if __name__ == "__main__":
    main()
