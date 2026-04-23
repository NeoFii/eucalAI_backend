# Deployment

Production deployment has moved to split multi-host compose files under [deploy/README.md](/home/luofei/backend/deploy/README.md).

## Compose Files

| File | Node | Services |
| --- | --- | --- |
| `deploy/docker-compose.backend.yml` | backend | `user-service`, `admin-service`, `user-worker`, MySQL, Redis |
| `deploy/docker-compose.router.yml` | router | `router-service` |
| `deploy/docker-compose.inference.yml` | GPU | `inference-service` |
| `deploy/docker-compose.local-infra.yml` | local dev only | MySQL, Redis |

## Primary Public Endpoint

Expose the router node as the public LLM gateway, typically behind `api.eucal.ai`:

```text
https://api.eucal.ai/v1/chat/completions
```

## Startup

Use the per-node env files in `deploy/env/`, then follow the staged startup documented in `deploy/README.md`.

## Runtime Config Assets

Router and inference still share:

- `deploy/router/runtime_config.json`
- `deploy/router/model_paths.json`
