# Eucal AI 官网后端 API

基于 FastAPI 构建的高性能异步后端服务。

## 技术栈

- **FastAPI**: 现代、高性能 Web 框架
- **Pydantic V2**: 数据验证与序列化
- **Uvicorn**: ASGI 服务器
- **UV**: Python 包管理器

## 快速开始

### 1. 安装 UV（如果尚未安装）

```bash
# Windows
pip install uv

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 创建虚拟环境并安装依赖

```bash
cd backend

# 创建虚拟环境（Python 3.10+）
uv venv --python python3.10

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 安装依赖
uv pip install -e ".[dev]"
```

### 3. 运行开发服务器

```bash
# 开发模式（热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. 查看 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── main.py          # FastAPI 应用入口
│   ├── config.py        # 配置管理
│   ├── api/             # API 路由
│   ├── core/            # 核心模块
│   ├── models/          # Pydantic 模型
│   ├── services/        # 业务逻辑
│   └── utils/           # 工具函数
├── tests/               # 测试目录
└── pyproject.toml       # 项目配置
```

## 开发命令

```bash
# 代码格式化
ruff format .

# 代码检查
ruff check .

# 类型检查
mypy app

# 运行测试
pytest

# 测试覆盖率
pytest --cov=app --cov-report=html
```
