# Service Runtime Contracts

## Environment

Required shared variables:

- `JWT_SECRET_KEY`
- `INTERNAL_SECRET`
- `ADMIN_DATABASE_URL`
- `USER_DATABASE_URL`

Router and inference do not require database URLs.

## Readiness

HTTP services expose `/health` and `/ready`.

```bash
python scripts/runtime_probe.py http-ready --port 8001
python scripts/runtime_probe.py http-ready --port 8003
python scripts/runtime_probe.py http-ready --port 8004
```

Data-owning services check their own database engine. Router and inference readiness
checks validate their own runtime dependencies.

## Internal Authentication

Internal backend calls use signed headers from `common.internal`:

- `X-Internal-Service`
- `X-Internal-Timestamp`
- `X-Internal-Signature`
- `X-Request-ID` when present

Allowed active caller relationships:

- user-service to admin internal endpoints
- admin-service to user internal endpoints
- router-service to user internal endpoints

Router to inference uses `X-Inference-Secret`.

## Schema Revision Gate

Every data-owning process verifies Alembic head before serving follow-up work. A
revision mismatch fails startup with a command hint for `uv run migrate`.
