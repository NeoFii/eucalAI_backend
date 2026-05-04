"""Business logic for routing settings (key-value)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.routing_setting_repository import RoutingSettingRepository
from schemas.routing_setting import RoutingSettingItem
from services.audit_service import AdminAuditService
from common.core.exceptions import NotFoundException, ValidationException

_logger = logging.getLogger(__name__)

FIVEWAY_ROUTE_ORDER = ["纠错", "工具调用", "通用任务", "任务拆解", "编程"]

_TIER_MODEL_KEY_RE = re.compile(r"^tier_[1-5]_model$")

_TYPE_VALIDATORS = {
    "float": lambda v: float(v),
    "int": lambda v: int(v),
    "string": lambda v: v,
}


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

    @staticmethod
    async def list_all(db: AsyncSession) -> dict[str, list[RoutingSettingItem]]:
        repo = RoutingSettingRepository(db)
        settings = await repo.get_all()
        grouped: dict[str, list[RoutingSettingItem]] = {}
        for s in settings:
            grouped.setdefault(s.group_name, []).append(_setting_item(s))
        return grouped

    @staticmethod
    async def get_setting(db: AsyncSession, key: str) -> RoutingSettingItem:
        setting = await RoutingSettingRepository(db).get_by_key(key)
        if setting is None:
            raise NotFoundException(f"setting '{key}' not found")
        return _setting_item(setting)

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
        return await RoutingSettingService.list_all(db)

    @staticmethod
    async def validate_tier_model_coverage(
        db: AsyncSession, items: list[tuple[str, str]],
    ) -> None:
        """Raise ValidationException if any tier model slug has no pool coverage."""
        from repositories.pool_repository import PoolRepository

        tier_models = [
            (k, v.strip()) for k, v in items
            if _TIER_MODEL_KEY_RE.match(k) and v.strip()
        ]
        if not tier_models:
            return

        slugs = list({v for _, v in tier_models})
        available = await PoolRepository(db).get_available_model_slugs()
        available_set = {row[0] for row in available}

        missing = []
        for key, slug in tier_models:
            if slug not in available_set:
                tier_num = key.replace("tier_", "").replace("_model", "")
                missing.append(f"tier {tier_num} 模型 '{slug}' 在号池中无可用通道")
        if missing:
            raise ValidationException("；".join(missing))

    @staticmethod
    async def resolve_for_internal(db: AsyncSession) -> dict[str, Any]:
        """Assemble routing settings into the dict format expected by router/inference services."""
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

        # `user_facing_aliases` is a comma-separated list. Empty / missing
        # falls back to ['auto']. The router-service normalizer will further
        # ensure `router_alias` itself is always present in the list.
        router_alias = kv.get("router_alias", "auto")
        raw_aliases = kv.get("user_facing_aliases", router_alias)
        user_facing_aliases = [a.strip() for a in raw_aliases.split(",") if a.strip()]
        if not user_facing_aliases:
            user_facing_aliases = [router_alias]

        return {
            "router_alias": router_alias,
            "user_facing_aliases": user_facing_aliases,
            "route_order": list(FIVEWAY_ROUTE_ORDER),
            "weights": weights,
            "score_bands": kv.get("score_bands", "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1"),
            "tier_model_map": tier_model_map,
        }
