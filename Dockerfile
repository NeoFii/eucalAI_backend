# 阶段1: 构建依赖
FROM python:3.11-slim AS builder

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# 复制依赖文件并安装
COPY pyproject.toml .
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --system fastapi uvicorn sqlalchemy aiomysql pydantic pydantic-settings python-jose passlib bcrypt python-multipart

# 阶段2: 生产运行
FROM python:3.11-slim AS runner

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# 复制虚拟环境（从 builder）
COPY --from=builder /app/.venv /app/.venv

# 复制应用代码
COPY --chown=appuser:appuser app/ /app/app/
COPY --chown=appuser:appuser .env.example /app/.env

# 设置环境
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
