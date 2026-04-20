# User Service Overview Refactor Design

**Date:** 2026-04-20
**Scope:** `user_service` phase 2 + phase 3 from `refactor/overview.md`, plus only the `common` infrastructure that `user_service` immediately depends on.

## Goal

Refactor `user_service` to introduce repository, policy, gateway, and schema-splitting boundaries without redesigning the external HTTP API.

## Explicit Compatibility Constraints

- Route paths stay unchanged.
- Request fields stay unchanged.
- Response changes are limited to:
  - user-facing billing responses stop exposing `operator_id`, `user_id`, and `ip`
  - `/billing/balance` adds `frozen_amount` and `available_balance`
- Permission changes are limited to:
  - pending users are blocked where `overview.md` requires
  - disabled users cannot reset password
- If other interface changes appear desirable during refactor, record them separately instead of implementing them here.

## Selected Approach

Use a staged compatibility refactor:

1. Add minimal `common` primitives used by `user_service`
2. Apply the new patterns to API Key flow first
3. Extend the same patterns to auth and billing flows
4. Delete only the old `user_service` compatibility layers that are replaced by the approved structure

This keeps the refactor incremental, testable, and attributable when failures happen.

## Scope Boundaries

### In Scope

- `common/db/base.py`: add `SoftDeleteMixin`
- `common/db/repository.py`: add `BaseRepository`
- `common/db/query.py`: add `ListParams` and `PaginatedResult`
- `common/gateway/base.py`: add `BaseGateway`
- `user_service/policies.py`
- `user_service/gateway.py`
- `user_service/repositories/`
- `user_service/schemas/`
- `user_service/services/*` refactor to use repositories/gateway
- `user_service/models/user_api_key.py` soft-delete support
- required Alembic migration(s)
- tests covering new behavior and compatibility

### Out of Scope

- refactoring other services to the same structure
- changing route layout or request contracts
- general API cleanup
- `backend_app` lifecycle changes unless a direct `user_service` dependency forces it

## Target Structure

```text
src/user_service/
├── dependencies.py          # identity only
├── policies.py              # authorization rules
├── gateway.py               # outgoing admin-service gateway + exported contracts
├── schemas/
│   ├── __init__.py
│   ├── common.py
│   ├── auth.py
│   ├── billing.py
│   ├── billing_admin.py
│   └── keys.py
├── repositories/
│   ├── __init__.py
│   ├── user_repository.py
│   ├── session_repository.py
│   ├── email_code_repository.py
│   ├── api_key_repository.py
│   ├── balance_tx_repository.py
│   ├── topup_order_repository.py
│   └── usage_stat_repository.py
└── services/
    ├── auth_service.py
    ├── api_key_service.py
    ├── balance_service.py
    ├── topup_order_service.py
    ├── usage_stat_service.py
    └── email_service.py
```

## Data-Flow Design

### API Key

- endpoints keep current path and request shape
- schemas move to `schemas/keys.py`
- `UserApiKey` adopts `SoftDeleteMixin`
- `ApiKeyRepository` becomes the default data-access path
- `ApiKeyService` keeps business rules only
- delete operations become soft-delete operations
- default list/count queries exclude deleted keys

### Auth

- `dependencies.py` only extracts token and resolves current user
- `policies.py` enforces active/pending/reset-password restrictions
- `gateway.py` absorbs the current admin-service HTTP client behavior
- auth endpoints keep current external route and request structure

### Billing

- user and admin response schemas split
- user-facing schemas become default-safe
- admin-facing schemas explicitly extend user-facing schemas
- repositories own list queries, filtering, and row-level lookup logic
- services keep transaction and business sequencing

## Compatibility Rules for Responses

- user-facing `TopupOrderItem` must not expose `user_id` or `operator_id`
- user-facing `UsageStatItem` must not expose `user_id`
- user-facing `ApiCallLogItem` must not expose `user_id` or `ip`
- admin-facing variants may include those internal fields
- `/billing/balance` must expose `balance`, `frozen_amount`, `used_amount`, `total_requests`, `total_tokens`, and computed `available_balance`

## Testing Strategy

- add unit tests for new `common` primitives
- add repository-focused API key tests
- preserve and update existing `user_service` compatibility tests
- add or update tests for:
  - pending-user restriction
  - disabled-user reset-password restriction
  - billing response field exposure
  - soft-delete API key query behavior

## Deletion Targets

- delete `src/user_service/services/admin_client.py` after `gateway.py` is adopted
- delete `src/user_service/schemas.py` after all endpoint/service imports move to `schemas/`

## Known Follow-Up Bucket

If implementation reveals desirable but non-approved HTTP contract cleanups, record them as follow-up items rather than changing them in this refactor.
