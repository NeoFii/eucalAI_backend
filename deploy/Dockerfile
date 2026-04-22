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
COPY --chown=appuser:appuser src/common/ /app/src/common/
COPY --chown=appuser:appuser src/user_service/ /app/src/user_service/
COPY --chown=appuser:appuser src/admin_service/ /app/src/admin_service/
COPY --chown=appuser:appuser src/router_service/ /app/src/router_service/
COPY --chown=appuser:appuser src/backend_app/ /app/src/backend_app/
COPY --chown=appuser:appuser migrations/ /app/migrations/
COPY --chown=appuser:appuser scripts/ /app/scripts/
COPY --chown=appuser:appuser deploy/router/ /app/deploy/router/
COPY --chown=appuser:appuser pyproject.toml README.md /app/
COPY --chown=appuser:appuser .env.example /app/.env.example

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000 8001 8003 8004

CMD ["/app/.venv/bin/uvicorn", "backend_app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
