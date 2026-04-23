# Phase 4 Operations

Phase 4 runtime operations now cover the split deployment topology documented in
`deploy/README.md`.

## Compose Orchestration

The deploy directory now provides:

- `deploy/docker-compose.backend.yml`
- `deploy/docker-compose.router.yml`
- `deploy/docker-compose.inference.yml`

All compose health checks use `/ready` through `scripts/runtime_probe.py http-ready`.

## Dependency Probe

This dependency probe section lists the runtime checks used during incidents.

Use these probes during incidents:

```bash
python scripts/runtime_probe.py http-ready --port 8000
python scripts/runtime_probe.py http-ready --port 8001
python scripts/runtime_probe.py worker-ready --database-url-env USER_DATABASE_URL --redis-url-env USER_QUEUE_REDIS_URL
python scripts/runtime_probe.py http-ready --port 8003
python scripts/runtime_probe.py http-ready --port 8004
```

The backend probes validate the standalone admin/user services plus the user worker.
Router and inference probes validate their own service readiness without database checks.

## Environment Checks

`uv run check-env` validates common secrets and the active data-owning URLs. A
generic `DATABASE_URL` is ignored and reported as a warning.

## Migration Checks

```bash
uv run migrate --service admin-service current --verbose
uv run migrate --service user-service current --verbose
uv run bootstrap-databases
```
