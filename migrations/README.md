# Service-Local Migrations

Each service owns an independent Alembic script location:

- `migrations/admin_service`
- `migrations/user_service`
- `migrations/router_service`
- `migrations/content_service`
- `migrations/testing_service`

Use the shared CLI wrapper:

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service revision -m "add new column" --autogenerate
```
