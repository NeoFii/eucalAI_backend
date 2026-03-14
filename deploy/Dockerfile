# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync --frozen --no-dev

FROM python:3.11-slim AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=appuser:appuser common/ /app/common/
COPY --chown=appuser:appuser user_service/ /app/user_service/
COPY --chown=appuser:appuser admin_service/ /app/admin_service/
COPY --chown=appuser:appuser testing_service/ /app/testing_service/
COPY --chown=appuser:appuser router_service/ /app/router_service/
COPY --chown=appuser:appuser content_service/ /app/content_service/
COPY --chown=appuser:appuser scripts/ /app/scripts/
COPY --chown=appuser:appuser pyproject.toml README.md /app/
COPY --chown=appuser:appuser .env.example /app/.env.example

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000 8001 8002 8003 8004 8012

CMD ["/app/.venv/bin/uvicorn", "user_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
