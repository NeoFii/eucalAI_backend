# Database Migrations

Alembic revisions are the only schema source of truth. Alembic revision files are
the 唯一 schema 真理 for this repository.

## Active Services

- `admin-service`
- `user-service`

## Commands

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run migrate --service admin-service revision -m "add column" --autogenerate
uv run bootstrap-databases
```

## Shared Environment

All service migration namespaces share `migrations/_env_shared.py`. Each service
directory contains a small `env.py` proxy, a `script.py.mako`, and a `versions/`
directory.

## SQL Snapshots

`scripts/sql/*.sql` files are snapshots for operations and ownership review. They are
not read by runtime code.
