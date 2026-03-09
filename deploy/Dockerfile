# 后端 Dockerfile - 使用 uv 管理依赖
# 多阶段构建，优化镜像大小

# ============================================================
# 阶段 1: 构建依赖
# ============================================================
FROM python:3.11-slim AS builder

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理器
RUN pip install --no-cache-dir uv

WORKDIR /app

# 复制依赖配置文件
COPY pyproject.toml uv.lock README.md ./

# 使用 uv sync 安装依赖（推荐方式）
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync --frozen --no-dev

# ============================================================
# 阶段 2: 生产运行
# ============================================================
FROM python:3.11-slim AS runner

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app

WORKDIR /app

# 从 builder 复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 复制应用代码（各服务模块）
COPY --chown=appuser:appuser common/ /app/common/
COPY --chown=appuser:appuser user/ /app/user/
COPY --chown=appuser:appuser admin/ /app/admin/
COPY --chown=appuser:appuser testing/ /app/testing/
COPY --chown=appuser:appuser pyproject.toml /app/
COPY --chown=appuser:appuser deploy/.env.example /app/.env

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 切换到非 root 用户
USER appuser

# 暴露端口（user:8000, admin:8001, testing:8002）
EXPOSE 8000 8001 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 默认启动用户服务，可通过 docker-compose command 覆盖
CMD ["/app/.venv/bin/uvicorn", "user.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]