# Eucal AI 后端

基于 FastAPI 构建的多服务异步后端，共三个独立服务进程共享同一数据库。

## 服务说明

| 服务 | 模块 | 端口 | 职责 |
| ---- | ---- | ---- | ---- |
| 用户服务 | `user/` | 8000 | 用户注册/登录/会话管理 |
| 管理员服务 | `admin/` | 8001 | 管理员认证、邀请码、新闻管理 |
| Testing 服务 | `testing/` | 8002 | 模型管理、供应商管理、性能探测 |

## 技术栈

- **FastAPI** + **Uvicorn** — Web 框架 / ASGI 服务器
- **SQLAlchemy 2.0**（异步）+ **aiomysql** — ORM / MySQL 驱动
- **Pydantic V2** — 数据验证
- **UV** — 包管理器

## 快速开始

### 1. 安装 UV

```bash
# Windows
pip install uv

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 安装依赖

```bash
cd backend
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填写以下必填项：
#   DATABASE_URL   — MySQL 连接地址
#   JWT_SECRET_KEY — 生产环境必须修改
```

### 4. 初始化数据库

```bash
# 在 MySQL 中执行全量建表脚本（包含所有三个服务的表）
mysql -u root -p eucal_ai < scripts/sql/init_tables.sql
```

### 5. 启动服务

```bash
# 启动全部服务（生产模式）
uv run start

# 启动全部服务（开发模式，自动重载）
uv run start --dev

# 仅启动指定服务
uv run start user testing

# 开发模式启动指定服务
uv run start --dev admin
```

启动后各服务的 API 文档（开发模式下可用）：

- 用户服务：<http://localhost:8000/docs>
- 管理员服务：<http://localhost:8001/docs>
- Testing 服务：<http://localhost:8002/docs>

## 项目结构

```text
backend/
├── admin/                  # 管理员服务（:8001）
│   ├── api/                # 路由和端点
│   ├── models/             # ORM 模型
│   ├── services/           # 业务逻辑
│   ├── config.py
│   └── main.py
├── user/                   # 用户服务（:8000）
│   ├── api/
│   ├── models/
│   ├── services/
│   ├── config.py
│   └── main.py
├── testing/                # Testing 服务（:8002）
│   ├── api/
│   ├── benchmark/          # 性能探测引擎
│   ├── models/
│   ├── services/
│   ├── config.py
│   └── main.py
├── common/                 # 三服务共享模块
│   ├── db/                 # SQLAlchemy 引擎 / 会话 / Base
│   ├── models/             # 跨服务共享模型（news）
│   ├── core/               # 异常定义 / 统一异常处理
│   ├── utils/              # JWT / 密码 / 雪花 ID / 时区
│   └── config.py           # 公共配置基类
├── scripts/
│   ├── start_services.py   # 一键启动脚本（uv run start 的入口）
│   └── sql/
│       ├── init_tables.sql # 全量建表语句（所有服务）
│       └── models.sql      # Testing 服务独立建表语句
├── tests/
├── .env.example
└── pyproject.toml
```

## 环境变量

所有服务共用根目录下的 `.env` 文件，关键配置项：

| 变量 | 说明 | 示例 |
| ---- | ---- | ---- |
| `DATABASE_URL` | MySQL 异步连接地址 | `mysql+aiomysql://root:pw@localhost:3306/eucal_ai` |
| `JWT_SECRET_KEY` | JWT 签名密钥（生产必改） | 随机长字符串 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | access token 有效期（分钟） | `15` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | refresh token 有效期（天） | `7` |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | 邮件服务（用于验证码） | — |
| `SNOWFLAKE_WORKER_ID` | 雪花 ID 工作节点（多实例需唯一） | `1` |
| `DEBUG` | 调试模式（启用 /docs） | `true` |

## 开发命令

```bash
# 代码格式化
uv run ruff format .

# 代码检查
uv run ruff check .

# 运行测试
uv run pytest

# 测试覆盖率
uv run pytest --cov=. --cov-report=html
```
