"""Seed routing configuration from runtime_config.json.

Reads the existing deploy/router/runtime_config.json, creates provider
credentials (encrypted) and a v1 routing config, then publishes it.

Usage:
    uv run seed-routing-config
    uv run seed-routing-config --config deploy/router/runtime_config.json
    uv run seed-routing-config --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "deploy" / "router" / "runtime_config.json"


def _resolve_env_var(value: str) -> str:
    """Resolve ${VAR} references in a string."""
    import re
    def _replace(m: re.Match) -> str:
        env_val = os.environ.get(m.group(1))
        if env_val is None:
            raise ValueError(f"env var {m.group(1)} not set")
        return env_val
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _replace, value)


async def _seed(config_path: Path, *, dry_run: bool = False) -> None:
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    model_providers: dict = raw.get("model_providers", {})
    if not model_providers:
        _logger.error("runtime_config.json has no model_providers")
        sys.exit(1)

    seen_creds: dict[str, str] = {}
    bindings: dict[str, dict] = {}

    for model_name, prov in model_providers.items():
        provider_slug = prov["provider_slug"]
        api_key_raw = prov["api_key"]
        api_base = prov["api_base"]
        upstream_model = prov["upstream_model"]

        try:
            api_key = _resolve_env_var(api_key_raw)
        except ValueError as exc:
            _logger.error("Cannot resolve %s for model %s: %s", api_key_raw, model_name, exc)
            sys.exit(1)

        cred_slug = f"{provider_slug}-main"
        if cred_slug not in seen_creds:
            seen_creds[cred_slug] = api_key
            _logger.info("Credential: %s (provider=%s)", cred_slug, provider_slug)

        bindings[model_name] = {
            "credential_slug": cred_slug,
            "api_base": _resolve_env_var(api_base) if "${" in api_base else api_base,
            "upstream_model": upstream_model,
        }

    config_data = {
        "router_alias": raw.get("router_alias", "auto"),
        "weights": raw.get("weights", {}),
        "score_bands": raw.get("score_bands", ""),
        "tier_model_map": raw.get("tier_model_map", {}),
        "model_provider_bindings": bindings,
    }

    _logger.info("Config data: %s", json.dumps(config_data, indent=2, ensure_ascii=False))

    if dry_run:
        _logger.info("Dry run — no database changes")
        return

    from admin_service.config import settings
    from admin_service.db import db_runtime
    from common.utils.crypto import encrypt_api_key, mask_api_key

    await db_runtime.init(settings.DATABASE_URL)
    async_session = db_runtime.session_factory

    async with async_session() as db:

        from admin_service.models.routing_config import ProviderCredential, RoutingConfig
        from admin_service.repositories.routing_config_repository import (
            ProviderCredentialRepository,
            RoutingConfigRepository,
        )

        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        cred_repo = ProviderCredentialRepository(db)

        for cred_slug, api_key in seen_creds.items():
            existing = await cred_repo.get_by_slug(cred_slug)
            if existing:
                _logger.info("Credential %s already exists, skipping", cred_slug)
                continue
            provider_slug = cred_slug.rsplit("-", 1)[0]
            enc = encrypt_api_key(api_key, master_key)
            cred = ProviderCredential(
                slug=cred_slug,
                provider_slug=provider_slug,
                api_key_enc=enc,
                mask=mask_api_key(api_key),
                is_active=True,
                remark="Seeded from runtime_config.json",
                created_by=1,
            )
            cred_repo.add(cred)
            _logger.info("Created credential: %s", cred_slug)

        await db.flush()

        existing_active = await RoutingConfigRepository(db).get_active()
        if existing_active:
            _logger.info("Active config v%d already exists, skipping", existing_active.version)
        else:
            config = RoutingConfig(
                status="draft",
                config_data=config_data,
                description="Seeded from runtime_config.json",
                created_by=1,
            )
            repo = RoutingConfigRepository(db)
            config = await repo.create_with_version_retry(config)
            await repo.publish(config, published_by=1)
            _logger.info("Published routing config v%d", config.version)

        await db.commit()

    await db_runtime.close()
    _logger.info("Seed complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed routing config from runtime_config.json")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH,
        help="Path to runtime_config.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    if not args.config.exists():
        _logger.error("Config file not found: %s", args.config)
        sys.exit(1)

    asyncio.run(_seed(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
