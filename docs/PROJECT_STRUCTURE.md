# Project Structure

```text
src/
  admin_service/       admin domain API, models, services, repositories
  common/              shared config, health, internal auth, db runtime
  inference_service/   DB-less inference API
  router_service/      DB-less LLM gateway
  user_service/        user auth, API keys, billing, usage stats

migrations/
  _env_shared.py
  admin_service/
  user_service/

scripts/
  bootstrap_service_databases.py
  check_service_environment.py
  migrate.py
  runtime_probe.py
  seed_routing_config.py
  start_services.py

deploy/
  README.md
  Dockerfile
  Dockerfile.inference
  Dockerfile.router-cpu
  docker-compose.backend.yml
  docker-compose.router.yml
  docker-compose.inference.yml
  docker-compose.local-infra.yml
  env/
  init-db.sql
  schema.snapshot.sql
  router/
```

Generated caches, virtual environments, and local worktrees are not part of the
project structure.
