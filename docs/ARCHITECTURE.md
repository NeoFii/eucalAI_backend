# Architecture

The active backend has two data-owning domains and two DB-less runtime services.

## Process Topology

| Process | Module | Port | Role |
| --- | --- | ---: | --- |
| user-service | `user_service.main:app` | 8000 | user control plane and billing API |
| admin-service | `admin_service.main:app` | 8001 | admin control plane and routing configuration API |
| router-service | `router_service.main:app` | 8003 | CPU request gateway and upstream routing |
| inference-service | `inference_service.main:app` | 8004 | model classification and routing signals |

## Data Ownership

| Domain | Package | Database | Tables |
| --- | --- | --- | --- |
| admin | `src/admin_service` | `ADMIN_DATABASE_URL` | `admin_users`, `admin_audit_logs`, `model_vendors`, `model_categories`, `supported_models`, `supported_model_category_map`, `routing_configs`, `provider_credentials` |
| user | `src/user_service` | `USER_DATABASE_URL` | `users`, `user_sessions`, `email_verification_codes`, `user_api_keys`, `balance_transactions`, `topup_orders`, `api_call_logs`, `usage_stats`, `voucher_redemption_codes` |

Router and inference do not own schemas. Router uses file-based runtime config under
`deploy/router/`.

## Request Flow

1. Frontend clients call `user-service`.
2. Admin clients call `admin-service`.
3. LLM clients call `router-service`.
4. Router validates user API keys through the user internal endpoint.
5. Router calls `inference-service` for classification.
6. Router forwards the request to the selected upstream provider.

## Internal Calls

Internal HTTP calls are signed with `common.internal` HMAC headers.

| Caller | Callee | Purpose |
| --- | --- | --- |
| admin-service | user internal API | user stats for admin views |
| router-service | user internal API | API key validation |

## Schema Management

Alembic is the only schema source of truth. Migration namespaces exist for:

- `migrations/admin_service`
- `migrations/user_service`

`uv run bootstrap-databases` upgrades both active schemas.

## Packaging

All importable packages live under `src/`. The base Dockerfile copies common,
admin, user, router, inference, migrations, scripts, and router runtime configuration
into the image.
