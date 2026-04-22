# Project Structure

```text
src/
  admin_service/       admin domain API, models, services, repositories
  backend_app/         consolidated admin + user FastAPI app
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
  start_services.py
  sql/
    admin_schema.sql
    user_schema.sql
    init_tables.sql

deploy/
  Dockerfile
  Dockerfile.inference
  Dockerfile.router-cpu
  docker-compose.yml
  router/
```

Generated caches, virtual environments, and local worktrees are not part of the
project structure.
