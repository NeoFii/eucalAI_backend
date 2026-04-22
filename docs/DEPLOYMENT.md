# Deployment

## Compose Topology

`deploy/docker-compose.yml` runs three active services:

| Container | Port | Image Source | Dependencies |
| --- | ---: | --- | --- |
| backend-app | 8001 | `deploy/Dockerfile` | external MySQL |
| router-service | 8003 | `deploy/Dockerfile.router-cpu` | inference-svc |
| inference-svc | 8004 | `deploy/Dockerfile.inference` | model weights |

MySQL is managed outside compose. Create the admin and user databases manually and
provide `ADMIN_DATABASE_URL` and `USER_DATABASE_URL`.

## Startup

```bash
uv run check-env
uv run bootstrap-databases
docker compose -f deploy/docker-compose.yml up -d
```

## Health Checks

Compose health checks call:

```bash
python scripts/runtime_probe.py http-ready --port 8001
python scripts/runtime_probe.py http-ready --port 8003
python scripts/runtime_probe.py http-ready --port 8004
```

`backend-app /ready` verifies only the admin and user database engines.

## Ports

| Port | Service | Exposure |
| ---: | --- | --- |
| 8000 | optional standalone user-service | local debugging |
| 8001 | backend-app or standalone admin-service | internal or public API gateway |
| 8003 | router-service | LLM API gateway |
| 8004 | inference-service | internal network only |

## Runtime Config

Router and inference share file-based routing assets:

- `deploy/router/runtime_config.json`
- `deploy/router/model_paths.json`

These files are copied into the relevant images and referenced with environment
variables such as `ROUTER_RUNTIME_CONFIG` and `ROUTER_MODEL_PATHS`.
