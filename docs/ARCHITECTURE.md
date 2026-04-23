# Architecture

The active backend has two data-owning domains and two DB-less runtime services.

## Process Topology

| Process | Module | Port | Role |
| --- | --- | ---: | --- |
| backend-app | `backend_app.main:app` | 8001 | consolidated admin and user control plane |
| router-service | `router_service.main:app` | 8003 | CPU request gateway and upstream routing |
| inference-service | `inference_service.main:app` | 8004 | model classification and routing signals |

Standalone `admin_service.main:app` and `user_service.main:app` remain available for
local domain debugging. They are not part of the default startup set.

## Data Ownership

| Domain | Package | Database | Tables |
| --- | --- | --- | --- |
| admin | `src/admin_service` | `ADMIN_DATABASE_URL` | `admin_users`, `admin_audit_logs`, `invitation_codes`, `model_vendors`, `model_categories`, `supported_models`, `supported_model_category_map`, `routing_configs`, `provider_credentials` |
| user | `src/user_service` | `USER_DATABASE_URL` | `users`, `user_sessions`, `email_verification_codes`, `user_api_keys`, `balance_transactions`, `topup_orders`, `api_call_logs`, `usage_stats`, `invitation_release_outbox`, `voucher_redemption_codes` |

Router and inference do not own schemas. Router uses file-based runtime config under
`deploy/router/`.

## Request Flow

1. Frontend and admin clients call `backend-app`.
2. LLM clients call `router-service`.
3. Router validates user API keys through the user internal endpoint.
4. Router calls `inference-service` for classification.
5. Router forwards the request to the selected upstream provider.

## Internal Calls

Internal HTTP calls are signed with `common.internal` HMAC headers.

| Caller | Callee | Purpose |
| --- | --- | --- |
| user-service | admin internal API | consume and release invitation codes |
| admin-service | user internal API | user stats for admin views |
| router-service | user internal API | API key validation |

## Schema Management

Alembic is the only schema source of truth. Migration namespaces exist for:

- `migrations/admin_service`
- `migrations/user_service`

`uv run bootstrap-databases` upgrades both active schemas.

## Packaging

All importable packages live under `src/`. The base Dockerfile copies common,
admin, user, router, inference, backend-app, migrations, scripts, and router runtime
configuration into the image.
