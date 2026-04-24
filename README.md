# Eucal AI Backend

This repository contains the active Eucal AI backend services.

## Phase 4 Status

The active Phase 4 runtime uses `/ready` probes, `X-Request-ID` propagation, and
signed internal calls between backend services.

## Active Services

| Service | Module | Port | Storage |
| --- | --- | ---: | --- |
| admin-service | `admin_service.main:app` | 8001 | admin MySQL schema |
| user-service | `user_service.main:app` | 8000 | user MySQL schema |
| router-service | `router_service.main:app` | 8003 | none |
| inference-service | `inference_service.main:app` | 8004 | none |

`admin-service` and `user-service` are separate control-plane services in the real
deployment topology. Each owns its own MySQL schema and exposes `/health` and `/ready`.

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
| `INTERNAL_SECRET` | admin, user, router | HMAC signing secret for internal calls |
| `ADMIN_DATABASE_URL` | admin-service | admin schema database URL |
| `USER_DATABASE_URL` | user-service | user schema database URL |
| `INFERENCE_SERVICE_SECRET` | router-service, inference-service | router to inference shared secret |

There is no generic `DATABASE_URL` fallback. Use service-specific database URLs.

## Migrations

Alembic revisions are the schema source of truth.

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run bootstrap-databases
```

`scripts/sql/*.sql` files are schema snapshots for operational reference only;
runtime code does not read them.

## Running Locally

```bash
uv run start
```

The default startup set is:

- `user-service`
- `admin-service`
- `inference-service`
- `router-service`
- `user-worker`

You can start a subset explicitly:

```bash
uv run start user-service admin-service router-service
```

## Deployment

Production deployment uses split multi-host compose files under `deploy/`:

- `deploy/docker-compose.backend.yml`
- `deploy/docker-compose.router.yml`
- `deploy/docker-compose.inference.yml`

See [deploy/README.md](/home/luofei/backend/deploy/README.md) for the final node layout,
env files, startup order, and `api.eucal.ai` gateway entrypoint.

## Runtime Contracts

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
