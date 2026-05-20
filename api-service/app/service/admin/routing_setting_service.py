"""Routing settings service (admin domain).

Ported from `services/admin-service/src/services/routing_setting_service.py`.
Phase 05-02 / Task 2 ported lines 1-185. Phase 08-01 / Task 1 ports
`resolve_for_internal` (lines 186-240) to support the internal HMAC endpoint
consumed by inference-service.

Rewrites applied (standard set):

- `from repositories.routing_setting_repository import RoutingSettingRepository` →
  `from app.repository.routing_setting_repository import RoutingSettingRepository`
- `from schemas.routing_setting import RoutingSettingItem` →
  `from app.schema.admin.routing_setting import RoutingSettingItem`
- `from services.audit_service import AdminAuditService` →
  `from app.service.admin.audit_service import AdminAuditService`
- `from common.core.exceptions import NotFoundException, ValidationException` →
  `from app.common.core.exceptions import NotFoundException, ValidationException`
- `from repositories.pool_repository import PoolRepository` →
  `from app.repository.pool_repository import PoolRepository`
- `from repositories.model_catalog_repository import SupportedModelRepository` →
  `from app.repository.model_catalog_repository import ModelCatalogRepository`
  (Phase 3 renamed the repository class)

D-06 (NEW): `_bump_version` increments the
`routing_config:version` key on Redis db/2 after every successful write.
Phase 6 will consume the version key in `RoutingConfigCache`. Fail-open
semantics (logger.warning on Redis errors; the business mutation still
commits).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import NotFoundException, ValidationException
from app.common.infra.cache import get_cache_redis
from app.repository.routing_setting_repository import RoutingSettingRepository
from app.schema.admin.routing_setting import RoutingSettingItem
from app.service.admin.audit_service import AdminAuditService

logger = logging.getLogger(__name__)

FIVEWAY_ROUTE_ORDER = ["纠错", "工具调用", "通用任务", "任务拆解", "编程"]

_TIER_MODEL_KEY_RE = re.compile(r"^tier_[1-5]_model$")

_TYPE_VALIDATORS = {
    "float": lambda v: float(v),
    "int": lambda v: int(v),
    "string": lambda v: v,
}

ROUTING_CONFIG_VERSION_KEY = "routing_config:version"


def _setting_item(s) -> RoutingSettingItem:
    return RoutingSettingItem(
        key=s.key,
        value=s.value,
        value_type=s.value_type,
        group_name=s.group_name,
        label=s.label,
        description=s.description,
        sort_order=s.sort_order,
        updated_at=s.updated_at,
    )


class RoutingSettingService:
    """List / read / update routing-config entries; D-06 version-bump hook."""

    # ------------------------------------------------------------------
    # D-06: version-key INCR (fail-open, post-commit)
    # ------------------------------------------------------------------

    @staticmethod
    async def _bump_version() -> None:
        """Increment `routing_config:version` after every successful
        routing-settings write (D-06).

        Phase 6 RoutingConfigCache will GET this key on every relay request
        and reload its in-memory copy when the version disagrees.  Phase 5
        ships the SIGNAL; the consumer arrives in Phase 6 (deliberate — no
        functional change in Phase 5 because no reader exists yet).
        """
        try:
            await get_cache_redis().incr(ROUTING_CONFIG_VERSION_KEY)
        except Exception:
            logger.warning("routing_config_version_bump_failed", exc_info=True)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    async def list_all(db: AsyncSession) -> dict[str, list[RoutingSettingItem]]:
        repo = RoutingSettingRepository(db)
        settings_rows = await repo.get_all()
        grouped: dict[str, list[RoutingSettingItem]] = {}
        for s in settings_rows:
            grouped.setdefault(s.group_name, []).append(_setting_item(s))
        return grouped

    @staticmethod
    async def get_setting(db: AsyncSession, key: str) -> RoutingSettingItem:
        setting = await RoutingSettingRepository(db).get_by_key(key)
        if setting is None:
            raise NotFoundException(f"setting '{key}' not found")
        return _setting_item(setting)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @staticmethod
    async def update_setting(
        db: AsyncSession,
        key: str,
        value: str,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingSettingItem:
        repo = RoutingSettingRepository(db)
        setting = await repo.get_by_key(key)
        if setting is None:
            raise NotFoundException(f"setting '{key}' not found")

        validator = _TYPE_VALIDATORS.get(setting.value_type)
        if validator:
            try:
                validator(value)
            except (ValueError, TypeError) as exc:
                raise ValidationException(
                    f"value '{value}' is not valid for type '{setting.value_type}': {exc}"
                ) from exc

        before_value = setting.value
        await repo.update_value(key, value, updated_by=actor_admin_id)
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="update_routing_setting",
            resource_type="routing_setting",
            resource_id=key,
            status="success",
            before_data={"key": key, "value": before_value},
            after_data={"key": key, "value": value},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await RoutingSettingService._bump_version()
        updated = await repo.get_by_key(key)
        return _setting_item(updated)

    @staticmethod
    async def batch_update(
        db: AsyncSession,
        items: list[tuple[str, str]],
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, list[RoutingSettingItem]]:
        repo = RoutingSettingRepository(db)
        before_data = {}
        for key, value in items:
            setting = await repo.get_by_key(key)
            if setting is None:
                raise NotFoundException(f"setting '{key}' not found")
            validator = _TYPE_VALIDATORS.get(setting.value_type)
            if validator:
                try:
                    validator(value)
                except (ValueError, TypeError) as exc:
                    raise ValidationException(
                        f"setting '{key}': value '{value}' invalid for type '{setting.value_type}': {exc}"
                    ) from exc
            before_data[key] = setting.value

        await repo.batch_update(items, updated_by=actor_admin_id)
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="batch_update_routing_settings",
            resource_type="routing_setting",
            resource_id="batch",
            status="success",
            before_data=before_data,
            after_data={k: v for k, v in items},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await RoutingSettingService._bump_version()
        return await RoutingSettingService.list_all(db)

    # ------------------------------------------------------------------
    # Validation (pre-write check used by both update + batch_update)
    # ------------------------------------------------------------------

    @staticmethod
    async def validate_tier_model_coverage(
        db: AsyncSession, items: list[tuple[str, str]],
    ) -> None:
        """Raise ValidationException if any tier_N_model slug has no pool
        coverage OR is missing a catalog `routing_slug`.

        Two-step check (matches source exactly):
        1. The slug must appear in `PoolRepository.get_available_model_slugs()`
           (i.e. at least one active pool offers it via an active account).
        2. The slug must exist in `ModelCatalog.routing_slug` (so the user
           catalog can describe it).
        """
        from app.repository.pool_repository import PoolRepository

        tier_models = [
            (k, v.strip()) for k, v in items
            if _TIER_MODEL_KEY_RE.match(k) and v.strip()
        ]
        if not tier_models:
            return

        available = await PoolRepository(db).get_available_model_slugs()
        available_set = {row[0] for row in available}

        missing = []
        for key, slug in tier_models:
            if slug not in available_set:
                tier_num = key.replace("tier_", "").replace("_model", "")
                missing.append(f"tier {tier_num} 模型 '{slug}' 在号池中无可用通道")
        if missing:
            raise ValidationException("；".join(missing))

        from app.repository.model_catalog_repository import (
            ModelCatalogRepository,
        )
        slugs_to_check = list({v for _, v in tier_models})
        existing_routing = await ModelCatalogRepository(db).get_routing_slugs_existing(
            slugs_to_check
        )
        catalog_missing = []
        for key, slug in tier_models:
            if slug not in existing_routing:
                tier_num = key.replace("tier_", "").replace("_model", "")
                catalog_missing.append(
                    f"tier {tier_num} 模型 '{slug}' 在模型目录中无对应 routing_slug，"
                    f"请先在模型管理中创建该模型并设置路由标识"
                )
        if catalog_missing:
            raise ValidationException("；".join(catalog_missing))

    # ------------------------------------------------------------------
    # Internal config resolution (Phase 8 — inference-service endpoint)
    # ------------------------------------------------------------------

    @staticmethod
    async def resolve_for_internal(db: AsyncSession) -> dict[str, Any]:
        """Assemble routing settings into the dict format expected by inference-service.

        Returns a flat dict with keys: router_alias, user_facing_aliases,
        route_order, weights, score_bands, tier_model_map, default_user_rpm,
        system_rpm_cap.
        """
        repo = RoutingSettingRepository(db)
        all_settings = await repo.get_all()
        kv = {s.key: s.value for s in all_settings}

        weights = {}
        for route in FIVEWAY_ROUTE_ORDER:
            w = kv.get(f"weight_{route}", "1.0")
            weights[route] = float(w)

        tier_model_map = {}
        for tier in range(1, 6):
            tier_model_map[str(tier)] = kv.get(f"tier_{tier}_model", "")

        router_alias = kv.get("router_alias", "auto")
        raw_aliases = kv.get("user_facing_aliases", router_alias)
        user_facing_aliases = [a.strip() for a in raw_aliases.split(",") if a.strip()]
        if not user_facing_aliases:
            user_facing_aliases = [router_alias]

        try:
            default_user_rpm = int(kv.get("default_user_rpm", "20") or "20")
        except (TypeError, ValueError):
            default_user_rpm = 20
        if default_user_rpm < 1:
            default_user_rpm = 20

        try:
            system_rpm_cap = int(kv.get("system_rpm_cap", "1000") or "1000")
        except (TypeError, ValueError):
            system_rpm_cap = 1000
        if system_rpm_cap < 1:
            system_rpm_cap = 1000

        return {
            "router_alias": router_alias,
            "user_facing_aliases": user_facing_aliases,
            "route_order": list(FIVEWAY_ROUTE_ORDER),
            "weights": weights,
            "score_bands": kv.get("score_bands", "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1"),
            "tier_model_map": tier_model_map,
            "default_user_rpm": default_user_rpm,
            "system_rpm_cap": system_rpm_cap,
        }


__all__ = ["ROUTING_CONFIG_VERSION_KEY", "RoutingSettingService"]
