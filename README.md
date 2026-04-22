# Eucal AI Backend

This repository contains the active Eucal AI backend services.

## Phase 4 Status

The active Phase 4 runtime uses `/ready` probes, `X-Request-ID` propagation, and
signed internal calls between backend services.

## Active Services

| Service | Module | Port | Storage |
| --- | --- | ---: | --- |
| backend-app | `backend_app.main:app` | 8001 | admin and user MySQL schemas |
| admin-service | `admin_service.main:app` | 8001 | admin MySQL schema |
| user-service | `user_service.main:app` | 8000 | user MySQL schema |
| router-service | `router_service.main:app` | 8003 | none |
| inference-service | `inference_service.main:app` | 8004 | none |

`backend-app` is the default control-plane process. It mounts the admin and user APIs,
initializes both database engines, verifies Alembic revisions, and exposes `/health`
and `/ready`.

`router-service` and `inference-service` are DB-less runtime services. Router reads
its model routing configuration from `deploy/router/runtime_config.json`; inference
loads model paths from `deploy/router/model_paths.json`.

## Setup

```bash
uv sync
cp .env.example .env
uv run check-env
uv run bootstrap-databases
```

Create the admin and user MySQL databases manually before running migrations. The
project does not create or drop databases automatically.

## Required Environment

| Variable | Required For | Purpose |
| --- | --- | --- |
| `JWT_SECRET_KEY` | all API services | JWT signing key, at least 32 characters |
| `INTERNAL_SECRET` | backend-app, admin, user, router | HMAC signing secret for internal calls |
| `ADMIN_DATABASE_URL` | backend-app, admin-service | admin schema database URL |
| `USER_DATABASE_URL` | backend-app, user-service | user schema database URL |
| `INFERENCE_SERVICE_SECRET` | router-service, inference-service | router to inference shared secret |

There is no generic `DATABASE_URL` fallback. Use service-specific database URLs.

## Migrations

Alembic revisions are the schema source of truth.

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run bootstrap-databases
```

`scripts/sql/*.sql` files are snapshots for operational reference; runtime code does
not read them.

## Running Locally

```bash
uv run start
```

The default startup set is:

- `backend-app`
- `inference-service`
- `router-service`

You can start a subset explicitly:

```bash
uv run start backend-app router-service
```

## Deployment

The compose topology is:

- `backend-app` on `8001`
- `router-service` on `8003`
- `inference-svc` on `8004`

Health checks use `scripts/runtime_probe.py http-ready` against `/ready`.

```bash
docker compose -f deploy/docker-compose.yml up -d
```

## Runtime Contracts

- `backend-app /ready` checks admin and user databases only.
- Admin internal endpoints accept signed calls from user-service.
- User internal endpoints accept signed calls from router-service and admin-service.
- Router calls inference through `X-Inference-Secret`.
- `X-Request-ID` is propagated by shared observability middleware where applicable.

## Super Admin Bootstrap

For first deploys, set:

```dotenv
BOOTSTRAP_SUPERADMIN_ENABLED=true
BOOTSTRAP_SUPERADMIN_EMAIL=founder@example.com
BOOTSTRAP_SUPERADMIN_PASSWORD=StrongPassword123!
BOOTSTRAP_SUPERADMIN_NAME=System Founder
```

After the first successful bootstrap, set `BOOTSTRAP_SUPERADMIN_ENABLED=false` and
keep `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=true`.
