# Database

The active backend owns two MySQL schemas.

| Schema | Owner | Purpose |
| --- | --- | --- |
| `eucal_ai_admin` | admin domain | administrators, audit logs, model catalog, routing configs, provider credentials |
| `eucal_ai_user` | user domain | users, sessions, API keys, billing ledger, usage stats, voucher redemption codes |

Router and inference are DB-less.

## Ownership Rules

- No cross-schema foreign keys.
- Cross-domain references are stored as IDs and validated by service contracts.
- Admin tables are migrated only by `migrations/admin_service`.
- User tables are migrated only by `migrations/user_service`.
- Runtime startup verifies each active schema is at Alembic head.

## Commands

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run bootstrap-databases
```

## Snapshots

`deploy/schema.snapshot.sql` is a combined schema snapshot for operational review.
It is not used by runtime startup and is not the source of truth.
