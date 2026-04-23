"""Business logic for routing configuration and provider credentials."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.config import settings
from admin_service.models.routing_config import ProviderCredential, RoutingConfig
from admin_service.repositories import (
    ProviderCredentialRepository,
    RoutingConfigRepository,
    SupportedModelRepository,
)
from admin_service.schemas.routing_config import (
    FIVEWAY_ROUTE_ORDER,
    CredentialCreate,
    CredentialItem,
    CredentialUpdate,
    InternalRoutingConfigFull,
    InternalRoutingConfigInference,
    RoutingConfigBrief,
    RoutingConfigCreate,
    RoutingConfigData,
    RoutingConfigItem,
    RoutingConfigUpdate,
)
from admin_service.services.audit_service import AdminAuditService
from common.core.exceptions import NotFoundException, ValidationException
from common.utils.crypto import decrypt_api_key, encrypt_api_key, mask_api_key

_logger = logging.getLogger(__name__)


def _parse_score_bands(raw: str) -> list[tuple[float, float, int]]:
    bands: list[tuple[float, float, int]] = []
    for item in raw.split(","):
        left, _, right = item.partition(":")
        if not left or not right:
            continue
        tier = int(right.strip())
        if "-" in left:
            start_raw, _, end_raw = left.partition("-")
            start = float(start_raw.strip())
            end = float(end_raw.strip())
        else:
            start = end = float(left.strip())
        if start > end:
            raise ValueError("score band start must be <= end")
        bands.append((start, end, tier))
    if not bands:
        raise ValueError("score bands must not be empty")
    return bands


def _safe_audit_data(cred: ProviderCredential) -> dict[str, Any]:
    return {
        "slug": cred.slug,
        "provider_slug": cred.provider_slug,
        "mask": cred.mask,
        "is_active": cred.is_active,
        "remark": cred.remark,
    }


def _credential_item(cred: ProviderCredential) -> CredentialItem:
    return CredentialItem(
        id=cred.id,
        slug=cred.slug,
        provider_slug=cred.provider_slug,
        mask=cred.mask,
        is_active=cred.is_active,
        remark=cred.remark,
        created_at=cred.created_at,
        updated_at=cred.updated_at,
    )


def _config_item(config: RoutingConfig) -> RoutingConfigItem:
    return RoutingConfigItem(
        id=config.id,
        version=config.version,
        status=config.status,
        description=config.description,
        config_data=config.config_data,
        published_at=config.published_at,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _config_brief(config: RoutingConfig) -> RoutingConfigBrief:
    return RoutingConfigBrief(
        id=config.id,
        version=config.version,
        status=config.status,
        description=config.description,
        published_at=config.published_at,
        created_at=config.created_at,
    )


class RoutingConfigService:
    """Manage routing configuration versions and provider credentials."""

    # ── Credential operations ────────────────────────────────────────

    @staticmethod
    async def create_credential(
        db: AsyncSession,
        payload: CredentialCreate,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CredentialItem:
        repo = ProviderCredentialRepository(db)
        if await repo.get_by_slug(payload.slug):
            raise ValidationException("credential slug already exists")

        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        enc = encrypt_api_key(payload.api_key, master_key)
        masked = mask_api_key(payload.api_key)

        cred = ProviderCredential(
            slug=payload.slug,
            provider_slug=payload.provider_slug,
            api_key_enc=enc,
            mask=masked,
            is_active=True,
            remark=payload.remark,
            created_by=actor_admin_id,
        )
        repo.add(cred)
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="create_provider_credential",
            resource_type="provider_credential",
            resource_id=payload.slug,
            status="success",
            after_data=_safe_audit_data(cred),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(cred)
        return _credential_item(cred)

    @staticmethod
    async def list_credentials(
        db: AsyncSession, *, page: int = 1, page_size: int = 50
    ) -> tuple[list[CredentialItem], int]:
        creds, total = await ProviderCredentialRepository(db).list_all(
            page=page, page_size=page_size
        )
        return [_credential_item(c) for c in creds], total

    @staticmethod
    async def update_credential(
        db: AsyncSession,
        slug: str,
        payload: CredentialUpdate,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CredentialItem:
        cred = await ProviderCredentialRepository(db).get_by_slug(slug)
        if cred is None:
            raise NotFoundException("credential not found")

        before = _safe_audit_data(cred)
        changed = payload.model_dump(exclude_unset=True)

        if "api_key" in changed:
            master_key = settings.PROVIDER_SECRET_MASTER_KEY
            cred.api_key_enc = encrypt_api_key(changed.pop("api_key"), master_key)
            cred.mask = mask_api_key(payload.api_key)
        for field, value in changed.items():
            setattr(cred, field, value)

        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="update_provider_credential",
            resource_type="provider_credential",
            resource_id=slug,
            status="success",
            before_data=before,
            after_data=_safe_audit_data(cred),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(cred)
        return _credential_item(cred)

    @staticmethod
    async def disable_credential(
        db: AsyncSession,
        slug: str,
        *,
        force: bool = False,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CredentialItem:
        cred = await ProviderCredentialRepository(db).get_by_slug(slug)
        if cred is None:
            raise NotFoundException("credential not found")
        if not cred.is_active:
            return _credential_item(cred)

        active_config = await RoutingConfigRepository(db).get_active()
        if active_config is not None:
            bindings = (active_config.config_data or {}).get("model_provider_bindings", {})
            referenced = any(
                b.get("credential_slug") == slug for b in bindings.values()
            )
            if referenced and not force:
                raise ValidationException(
                    f"credential '{slug}' is referenced by active config v{active_config.version}; "
                    "use force=true to override"
                )

        before = _safe_audit_data(cred)
        cred.is_active = False
        action = "force_disable_provider_credential" if force else "disable_provider_credential"
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action=action,
            resource_type="provider_credential",
            resource_id=slug,
            status="success",
            before_data=before,
            after_data=_safe_audit_data(cred),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(cred)
        return _credential_item(cred)

    # ── Config validation helpers ────────────────────────────────────

    @staticmethod
    async def _validate_config_data(
        db: AsyncSession,
        data: RoutingConfigData,
        *,
        check_model_catalog: bool = False,
    ) -> None:
        try:
            _parse_score_bands(data.score_bands)
        except ValueError as exc:
            raise ValidationException(f"invalid score_bands: {exc}") from exc

        tier_models = set(data.tier_model_map.values())
        bound_models = set(data.model_provider_bindings.keys())
        missing_bindings = tier_models - bound_models
        if missing_bindings:
            raise ValidationException(
                f"model_provider_bindings missing for: {', '.join(sorted(missing_bindings))}"
            )

        cred_slugs = [b.credential_slug for b in data.model_provider_bindings.values()]
        cred_repo = ProviderCredentialRepository(db)
        active_creds = await cred_repo.get_active_by_slugs(cred_slugs)
        missing_creds = set(cred_slugs) - set(active_creds.keys())
        if missing_creds:
            raise ValidationException(
                f"credential slugs not found or inactive: {', '.join(sorted(missing_creds))}"
            )

        if check_model_catalog:
            model_repo = SupportedModelRepository(db)
            for model_slug in tier_models:
                model = await model_repo.get_by_slug(model_slug, active_only=True)
                if model is None:
                    raise ValidationException(
                        f"model '{model_slug}' not found or inactive in model catalog"
                    )

    # ── Config CRUD ──────────────────────────────────────────────────

    @staticmethod
    async def create_version(
        db: AsyncSession,
        payload: RoutingConfigCreate,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingConfigItem:
        await RoutingConfigService._validate_config_data(db, payload.config_data)

        config = RoutingConfig(
            status="draft",
            config_data=payload.config_data.model_dump(),
            description=payload.description,
            created_by=actor_admin_id,
        )
        config = await RoutingConfigRepository(db).create_with_version_retry(config)
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="create_routing_config",
            resource_type="routing_config",
            resource_id=str(config.version),
            status="success",
            after_data={"version": config.version, "description": config.description},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(config)
        return _config_item(config)

    @staticmethod
    async def get_version(db: AsyncSession, version: int) -> RoutingConfigItem:
        config = await RoutingConfigRepository(db).get_by_version(version)
        if config is None:
            raise NotFoundException(f"routing config v{version} not found")
        return _config_item(config)

    @staticmethod
    async def get_active(db: AsyncSession) -> RoutingConfigItem:
        config = await RoutingConfigRepository(db).get_active()
        if config is None:
            raise NotFoundException("no active routing config")
        return _config_item(config)

    @staticmethod
    async def list_versions(
        db: AsyncSession, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[RoutingConfigBrief], int]:
        configs, total = await RoutingConfigRepository(db).list_versions(
            page=page, page_size=page_size
        )
        return [_config_brief(c) for c in configs], total

    @staticmethod
    async def update_version(
        db: AsyncSession,
        version: int,
        payload: RoutingConfigUpdate,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingConfigItem:
        config = await RoutingConfigRepository(db).get_by_version(version)
        if config is None:
            raise NotFoundException(f"routing config v{version} not found")
        if config.status != "draft":
            raise ValidationException("only draft versions can be edited")

        if payload.config_data is not None:
            await RoutingConfigService._validate_config_data(db, payload.config_data)
            config.config_data = payload.config_data.model_dump()
        if payload.description is not None:
            config.description = payload.description

        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="update_routing_config",
            resource_type="routing_config",
            resource_id=str(version),
            status="success",
            after_data={"version": version},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(config)
        return _config_item(config)

    # ── Publish / Rollback ───────────────────────────────────────────

    @staticmethod
    async def publish_version(
        db: AsyncSession,
        version: int,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingConfigItem:
        repo = RoutingConfigRepository(db)
        config = await repo.get_by_version(version)
        if config is None:
            raise NotFoundException(f"routing config v{version} not found")
        if config.status == "active":
            return _config_item(config)
        if config.status != "draft":
            raise ValidationException("only draft versions can be published")

        config_data = RoutingConfigData.model_validate(config.config_data)
        await RoutingConfigService._validate_config_data(
            db, config_data, check_model_catalog=True
        )

        await repo.publish(config, published_by=actor_admin_id)
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="publish_routing_config",
            resource_type="routing_config",
            resource_id=str(version),
            status="success",
            after_data={"version": version, "status": "active"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(config)
        return _config_item(config)

    @staticmethod
    async def rollback_to_version(
        db: AsyncSession,
        version: int,
        *,
        actor_admin_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RoutingConfigItem:
        source = await RoutingConfigRepository(db).get_by_version(version)
        if source is None:
            raise NotFoundException(f"routing config v{version} not found")

        config_data = RoutingConfigData.model_validate(source.config_data)
        await RoutingConfigService._validate_config_data(
            db, config_data, check_model_catalog=True
        )

        new_config = RoutingConfig(
            status="draft",
            config_data=source.config_data,
            description=f"Rollback to v{version}",
            created_by=actor_admin_id,
        )
        repo = RoutingConfigRepository(db)
        new_config = await repo.create_with_version_retry(new_config)
        await repo.publish(new_config, published_by=actor_admin_id)

        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=None,
            action="rollback_routing_config",
            resource_type="routing_config",
            resource_id=str(new_config.version),
            status="success",
            after_data={
                "new_version": new_config.version,
                "source_version": version,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(new_config)
        return _config_item(new_config)

    # ── Internal endpoint helpers ────────────────────────────────────

    @staticmethod
    async def resolve_active_full(db: AsyncSession) -> InternalRoutingConfigFull:
        config = await RoutingConfigRepository(db).get_active()
        if config is None:
            raise NotFoundException("no active routing config")

        data = config.config_data
        bindings = data.get("model_provider_bindings", {})
        cred_slugs = list({b["credential_slug"] for b in bindings.values()})
        cred_repo = ProviderCredentialRepository(db)
        active_creds = await cred_repo.get_active_by_slugs(cred_slugs)

        missing = set(cred_slugs) - set(active_creds.keys())
        if missing:
            raise ValidationException(
                f"active config references disabled credentials: {', '.join(sorted(missing))}"
            )

        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        model_providers: dict[str, dict[str, str]] = {}
        for model_name, binding in bindings.items():
            cred = active_creds[binding["credential_slug"]]
            enc = cred.api_key_enc
            api_key = decrypt_api_key(enc["ciphertext"], enc["iv"], enc["tag"], master_key)
            model_providers[model_name] = {
                "provider_slug": cred.provider_slug,
                "api_key": api_key,
                "api_base": binding["api_base"],
                "upstream_model": binding["upstream_model"],
            }

        return InternalRoutingConfigFull(
            version=config.version,
            status=config.status,
            router_alias=data.get("router_alias", "auto"),
            route_order=list(FIVEWAY_ROUTE_ORDER),
            weights=data.get("weights", {}),
            score_bands=data.get("score_bands", ""),
            tier_model_map=data.get("tier_model_map", {}),
            model_providers=model_providers,
        )

    @staticmethod
    async def resolve_active_inference(db: AsyncSession) -> InternalRoutingConfigInference:
        config = await RoutingConfigRepository(db).get_active()
        if config is None:
            raise NotFoundException("no active routing config")

        data = config.config_data
        return InternalRoutingConfigInference(
            version=config.version,
            status=config.status,
            route_order=list(FIVEWAY_ROUTE_ORDER),
            weights=data.get("weights", {}),
            score_bands=data.get("score_bands", ""),
            tier_model_map=data.get("tier_model_map", {}),
        )



