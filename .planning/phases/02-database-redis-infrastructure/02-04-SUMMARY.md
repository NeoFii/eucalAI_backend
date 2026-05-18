# Plan 02-04 Summary: Alembic init and baseline migration

## Outcome: COMPLETE

All 6 tasks executed and committed atomically.

## What Was Done

1. **alembic.ini** — Created with `service_package=api_service`, `database_env=DATABASE_URL`
2. **env.py** — Thin proxy calling `_env_shared.run_env()`
3. **script.py.mako** — Standard Alembic migration template
4. **versions/__init__.py** — Empty package marker
5. **models/__init__.py** — Placeholder docstring for Phase 3 ORM models
6. **20260519_baseline.py** — Consolidated baseline with all 22 tables

## Baseline Migration Details

The baseline migration merges the final state of both databases:

- **User-domain (9 tables):** users, email_verification_codes, user_sessions, user_api_keys, balance_transactions, topup_orders, api_call_logs, usage_stats, voucher_redemption_codes
- **Admin-domain (13 tables):** admin_users, audit_action_definitions, admin_audit_logs, model_vendors, model_categories, model_catalog, model_catalog_category_map, routing_configs, provider_credentials, routing_settings, pools, pool_model_configs, pool_accounts

Key schema decisions reflected:
- All monetary fields use BIGINT (micro-yuan precision)
- Table renames applied: model_catalog, pool_model_configs, model_catalog_category_map
- Price columns renamed: sale_input_per_million, cost_input_per_million, etc.
- api_call_logs refactored to 14 core columns + log_type ENUM + other JSON
- users.record_ip_log column included
- All CHECK constraints, FK constraints, and composite indexes present
- Seed data for model_vendors (4), model_categories (4), audit_action_definitions (50)

## Commits

1. `d9834cf` feat(02-04): add alembic.ini for api-service migrations
2. `dfc1505` feat(02-04): add migrations/env.py proxy
3. `e96aef9` feat(02-04): add script.py.mako migration template
4. `7e42db6` feat(02-04): add versions/__init__.py package marker
5. `1a0ff61` feat(02-04): add models/__init__.py placeholder for Phase 3
6. `28f5f33` feat(02-04): add baseline migration with all 22 tables

## Verification

- Python syntax: PASS
- All 22 CREATE TABLE IF NOT EXISTS statements present
- All 22 tables in downgrade DROP list (FK reverse order)
- Ruff lint: PASS
- Key column names verified (sale_*, cost_*, quota, log_type, record_ip_log)

## Phase 2 Status

All 4 plans complete. Phase 2 (Database & Redis Infrastructure) is DONE.
