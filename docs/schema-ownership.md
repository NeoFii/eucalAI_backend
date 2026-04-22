# Schema Ownership

Alembic revisions are the schema source of truth. SQL snapshots are operational
references only.

## Active Owners

| Owner | Migration Namespace | Snapshot | Database Env |
| --- | --- | --- | --- |
| admin | `migrations/admin_service` | `scripts/sql/admin_schema.sql` | `ADMIN_DATABASE_URL` |
| user | `migrations/user_service` | `scripts/sql/user_schema.sql` | `USER_DATABASE_URL` |

Admin-owned objects include `admin_users`, `admin_audit_logs`,
`invitation_codes`, `model_vendors`, `model_categories`, `supported_models`,
and `supported_model_category_map`.

User-owned objects include `users`, `user_api_keys`,
`voucher_redemption_codes`, `usage_stats`, billing ledger tables, and
invitation outbox tables.

## Bootstrap Order

`scripts/sql/init_tables.sql` sources snapshots in this order:

1. admin
2. user

`uv run bootstrap-databases` applies Alembic migrations for both active services.

## Rules

- A table belongs to exactly one service.
- No runtime service may create tables directly.
- No generic `DATABASE_URL` fallback is allowed.
- Router and inference remain DB-less.
