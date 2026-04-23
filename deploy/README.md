# Deployment Layout

This directory contains the split multi-host deployment for the agreed production topology:

- backend node: `user-service`, `admin-service`, `user-worker`, MySQL, Redis
- router node: `router-service`
- GPU node: `inference-service`

All service-to-service traffic is expected to stay inside one cloud VPC/private network.

## Files

- `docker-compose.backend.yml` - backend node services and stateful dependencies
- `docker-compose.router.yml` - public LLM gateway on the router node
- `docker-compose.inference.yml` - GPU inference node
- `docker-compose.local-infra.yml` - local MySQL + Redis only, for host-based development
- `env/backend.env.example` - backend node environment template
- `env/router.env.example` - router node environment template
- `env/inference.env.example` - inference node environment template
- `init-db.sql` - first-boot MySQL schema creation
- `router/runtime_config.json` - router runtime policy fallback
- `router/model_paths.json` - inference model asset paths inside the container

## Public Endpoints

Recommended public DNS layout:

- `api.eucal.ai` -> router node -> `router-service:8003`
- `user-api.eucal.ai` -> backend node -> `user-service:8000`
- `admin-api.eucal.ai` -> backend node -> `admin-service:8001`

Router already exposes OpenAI-compatible endpoints under `/v1/*`, so the primary client entrypoint is:

```text
https://api.eucal.ai/v1/chat/completions
```

## Internal Topology

```text
router-service  -> user-service      (API key validation, call logs)
router-service  -> admin-service     (routing config)
router-service  -> inference-service (classification)
inference-service -> admin-service   (routing config)
admin-service   -> user-service      (admin user-management data)
```

## Environment Setup

Copy the example file that matches each node:

```bash
cp deploy/env/backend.env.example deploy/env/backend.env
cp deploy/env/router.env.example deploy/env/router.env
cp deploy/env/inference.env.example deploy/env/inference.env
```

Fill in real secrets and private hostnames or VPC IPs before starting containers.

## Backend Node

Bring up stateful dependencies first:

```bash
docker compose --env-file deploy/env/backend.env -f deploy/docker-compose.backend.yml up -d mysql redis
```

Run migrations:

```bash
docker compose --env-file deploy/env/backend.env -f deploy/docker-compose.backend.yml run --rm admin-service python scripts/migrate.py --service admin-service upgrade head
docker compose --env-file deploy/env/backend.env -f deploy/docker-compose.backend.yml run --rm user-service python scripts/migrate.py --service user-service upgrade head
```

Start the backend APIs and worker:

```bash
docker compose --env-file deploy/env/backend.env -f deploy/docker-compose.backend.yml up -d user-service admin-service user-worker
```

## GPU Node

Place the model weights on the host at the path configured by `MODEL_WEIGHTS_HOST_PATH`.
The container mounts that directory to `/app/models`, and `deploy/router/model_paths.json`
must match the directory layout inside `/app/models`.

Start inference:

```bash
docker compose --env-file deploy/env/inference.env -f deploy/docker-compose.inference.yml up -d
```

## Router Node

Start the public API gateway:

```bash
docker compose --env-file deploy/env/router.env -f deploy/docker-compose.router.yml up -d
```

Terminate TLS at the cloud load balancer or a reverse proxy in front of `router-service:8003`.

## Health Checks

- backend user API: `python scripts/runtime_probe.py http-ready --port 8000`
- backend admin API: `python scripts/runtime_probe.py http-ready --port 8001`
- backend worker: `python scripts/runtime_probe.py worker-ready --database-url-env USER_DATABASE_URL --redis-url-env USER_QUEUE_REDIS_URL`
- router: `python scripts/runtime_probe.py http-ready --port 8003`
- inference: `python scripts/runtime_probe.py http-ready --port 8004`

## Security Groups

- expose `8003` to the public internet only through HTTPS ingress
- allow router node -> backend node `8000`, `8001`
- allow router node -> GPU node `8004`
- allow GPU node -> backend node `8001`
- keep MySQL and Redis private to the backend node's Docker network or private subnet only

## Persistent Data Ownership

- `user-service` database: users, API keys, call logs, usage stats, billing data
- `admin-service` database: routing config, provider credentials, model catalog, admin audit
- `router-service`: stateless, no database required in this deployment

