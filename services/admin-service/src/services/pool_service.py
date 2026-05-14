"""Business logic for pool management."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.enums import PoolAccountStatus
from common.internal import get_internal_client
from models.pool import Pool, PoolAccount, PoolModel
from repositories.pool_repository import (
    PoolAccountRepository,
    PoolModelRepository,
    PoolRepository,
)
from schemas.pool import (
    AccountBalanceResult,
    CheckBalancesResult,
    PoolAccountCreate,
    PoolAccountItem,
    PoolAccountUpdate,
    PoolCreate,
    PoolDetail,
    PoolItem,
    PoolModelCreate,
    PoolModelItem,
    PoolModelUpdate,
    PoolUpdate,
    SyncModelsResult,
)
from services.audit_service import AdminAuditService
from common.core.exceptions import NotFoundException, ValidationException
from common.utils.crypto import decrypt_api_key, encrypt_api_key, mask_api_key

logger = logging.getLogger(__name__)


def _pool_model_item(m: PoolModel) -> PoolModelItem:
    return PoolModelItem(
        id=m.id, model_slug=m.model_slug, upstream_model_id=m.upstream_model_id,
        cost_input_per_million=m.cost_input_per_million,
        cost_output_per_million=m.cost_output_per_million,
        cost_cached_input_per_million=m.cost_cached_input_per_million,
        context_length=m.context_length, is_enabled=m.is_enabled,
    )


def _pool_account_item(a: PoolAccount) -> PoolAccountItem:
    return PoolAccountItem(
        id=a.id, name=a.name, mask=a.mask, balance=a.balance,
        status=a.status, rpm_limit=a.rpm_limit, tpm_limit=a.tpm_limit,
        weight=a.weight, last_checked_at=a.last_checked_at,
        remark=a.remark, created_at=a.created_at, updated_at=a.updated_at,
    )


def _pool_item(p: Pool) -> PoolItem:
    return PoolItem(
        id=p.id, slug=p.slug, name=p.name, base_url=p.base_url,
        is_enabled=p.is_enabled, priority=p.priority, weight=p.weight,
        health_check_endpoint=p.health_check_endpoint, remark=p.remark,
        model_count=len(p.models or []),
        account_count=len(p.accounts or []),
        created_at=p.created_at, updated_at=p.updated_at,
    )


def _pool_detail(p: Pool) -> PoolDetail:
    return PoolDetail(
        id=p.id, slug=p.slug, name=p.name, base_url=p.base_url,
        is_enabled=p.is_enabled, priority=p.priority, weight=p.weight,
        health_check_endpoint=p.health_check_endpoint, remark=p.remark,
        models=[_pool_model_item(m) for m in (p.models or [])],
        accounts=[_pool_account_item(a) for a in (p.accounts or [])],
        created_at=p.created_at, updated_at=p.updated_at,
    )


def _safe_pool_audit(p: Pool) -> dict[str, Any]:
    return {
        "slug": p.slug, "name": p.name, "base_url": p.base_url,
        "is_enabled": p.is_enabled, "priority": p.priority, "weight": p.weight,
    }


def _extract_balance(body: dict) -> int:
    """Parse upstream balance response into micro-yuan (1 yuan = 1,000,000)."""
    data = body.get("data", body)
    if isinstance(data, dict):
        for key in ("total_remain", "points", "balance", "remain"):
            if key in data:
                return int(float(data[key]) * 1_000_000)
    if isinstance(data, (int, float)):
        return int(float(data) * 1_000_000)
    if isinstance(body, dict) and "balance" in body:
        return int(float(body["balance"]) * 1_000_000)
    return 0


def _extract_model_pricing(item: dict) -> tuple[int, int]:
    """Extract input/output price in micro-yuan per million from upstream model item.

    Supports aiping format: price.input_price_range / output_price_range (元/M).
    """
    price = item.get("price")
    if not isinstance(price, dict):
        return 0, 0
    input_range = price.get("input_price_range")
    output_range = price.get("output_price_range")
    input_price = int(float(input_range[0]) * 1_000_000) if isinstance(input_range, list) and input_range else 0
    output_price = int(float(output_range[0]) * 1_000_000) if isinstance(output_range, list) and output_range else 0
    return input_price, output_price


class PoolService:

    # ------------------------------------------------------------------
    # Pool CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_pool(
        db: AsyncSession, payload: PoolCreate, *,
        actor_admin_id: int,
    ) -> PoolItem:
        repo = PoolRepository(db)
        if await repo.get_by_slug(payload.slug):
            raise ValidationException("pool slug already exists")

        pool = Pool(
            slug=payload.slug, name=payload.name, base_url=payload.base_url,
            priority=payload.priority, weight=payload.weight,
            health_check_endpoint=payload.health_check_endpoint,
            remark=payload.remark, created_by=actor_admin_id,
        )
        repo.add(pool)
        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="create_pool", resource_type="pool",
            resource_id=payload.slug, status="success",
            after_data=_safe_pool_audit(pool),
        )
        await db.commit()
        await db.refresh(pool)
        return _pool_item(pool)

    @staticmethod
    async def list_pools(
        db: AsyncSession, *, page: int = 1, page_size: int = 50,
    ) -> tuple[list[PoolItem], int]:
        pools, total = await PoolRepository(db).list_pools(page=page, page_size=page_size)
        return [_pool_item(p) for p in pools], total

    @staticmethod
    async def get_pool(db: AsyncSession, slug: str) -> PoolDetail:
        pool = await PoolRepository(db).get_by_slug(slug)
        if pool is None:
            raise NotFoundException("pool not found")
        return _pool_detail(pool)

    @staticmethod
    async def update_pool(
        db: AsyncSession, slug: str, payload: PoolUpdate, *,
        actor_admin_id: int,
    ) -> PoolItem:
        pool = await PoolRepository(db).get_by_slug(slug)
        if pool is None:
            raise NotFoundException("pool not found")

        before = _safe_pool_audit(pool)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(pool, field, value)
        pool.updated_by = actor_admin_id

        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="update_pool", resource_type="pool",
            resource_id=slug, status="success",
            before_data=before, after_data=_safe_pool_audit(pool),
        )
        await db.commit()
        await db.refresh(pool)
        return _pool_item(pool)

    @staticmethod
    async def disable_pool(
        db: AsyncSession, slug: str, *,
        actor_admin_id: int,
    ) -> PoolItem:
        pool = await PoolRepository(db).get_by_slug(slug)
        if pool is None:
            raise NotFoundException("pool not found")
        if not pool.is_enabled:
            return _pool_item(pool)

        before = _safe_pool_audit(pool)
        pool.is_enabled = False
        pool.updated_by = actor_admin_id
        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="disable_pool", resource_type="pool",
            resource_id=slug, status="success",
            before_data=before, after_data=_safe_pool_audit(pool),
        )
        await db.commit()
        await db.refresh(pool)
        return _pool_item(pool)

    # ------------------------------------------------------------------
    # PoolModel CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_pool_or_raise(db: AsyncSession, slug: str) -> Pool:
        pool = await PoolRepository(db).get_by_slug(slug)
        if pool is None:
            raise NotFoundException("pool not found")
        return pool

    @staticmethod
    async def add_pool_model(
        db: AsyncSession, pool_slug: str, payload: PoolModelCreate, *,
        actor_admin_id: int,
    ) -> PoolModelItem:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)
        repo = PoolModelRepository(db)
        if await repo.get_by_pool_and_model(pool.id, payload.model_slug):
            raise ValidationException(f"pool '{pool_slug}' already has model '{payload.model_slug}'")

        pm = PoolModel(
            pool_id=pool.id, model_slug=payload.model_slug,
            upstream_model_id=payload.upstream_model_id,
            cost_input_per_million=payload.cost_input_per_million,
            cost_output_per_million=payload.cost_output_per_million,
            cost_cached_input_per_million=payload.cost_cached_input_per_million,
            context_length=payload.context_length,
        )
        repo.add(pm)
        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="add_pool_model", resource_type="pool_model",
            resource_id=f"{pool_slug}/{payload.model_slug}", status="success",
            after_data={"pool_slug": pool_slug, "model_slug": payload.model_slug, "upstream_model_id": payload.upstream_model_id},
        )
        await db.commit()
        await db.refresh(pm)
        return _pool_model_item(pm)

    @staticmethod
    async def update_pool_model(
        db: AsyncSession, pool_slug: str, model_slug: str, payload: PoolModelUpdate, *,
        actor_admin_id: int,
    ) -> PoolModelItem:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)
        repo = PoolModelRepository(db)
        pm = await repo.get_by_pool_and_model(pool.id, model_slug)
        if pm is None:
            raise NotFoundException(f"model '{model_slug}' not found on pool '{pool_slug}'")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(pm, field, value)

        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="update_pool_model", resource_type="pool_model",
            resource_id=f"{pool_slug}/{model_slug}", status="success",
            after_data={"pool_slug": pool_slug, "model_slug": model_slug},
        )
        await db.commit()
        await db.refresh(pm)
        return _pool_model_item(pm)

    @staticmethod
    async def remove_pool_model(
        db: AsyncSession, pool_slug: str, model_slug: str, *,
        actor_admin_id: int,
    ) -> None:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)

        from repositories.routing_setting_repository import RoutingSettingRepository
        referencing_tiers = await RoutingSettingRepository(db).get_tier_keys_by_model_slug(
            model_slug
        )
        if referencing_tiers:
            available = await PoolRepository(db).get_available_model_slugs()
            other_pools = [
                name for slug, name in available
                if slug == model_slug and name != pool.name
            ]
            if not other_pools:
                tier_list = ", ".join(referencing_tiers)
                raise ValidationException(
                    f"无法移除模型 '{model_slug}'：它正被路由配置 [{tier_list}] 引用，"
                    f"且没有其他号池提供该模型的通道"
                )

        removed = await PoolModelRepository(db).remove(pool.id, model_slug)
        if not removed:
            raise NotFoundException(f"model '{model_slug}' not found on pool '{pool_slug}'")

        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="remove_pool_model", resource_type="pool_model",
            resource_id=f"{pool_slug}/{model_slug}", status="success",
            before_data={"pool_slug": pool_slug, "model_slug": model_slug},
        )
        await db.commit()

    # ------------------------------------------------------------------
    # PoolAccount CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def add_pool_account(
        db: AsyncSession, pool_slug: str, payload: PoolAccountCreate, *,
        actor_admin_id: int,
    ) -> PoolAccountItem:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)
        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        enc = encrypt_api_key(payload.api_key, master_key)
        masked = mask_api_key(payload.api_key)

        account = PoolAccount(
            pool_id=pool.id, name=payload.name,
            api_key_enc=enc, mask=masked,
            balance=payload.balance, weight=payload.weight,
            rpm_limit=payload.rpm_limit, tpm_limit=payload.tpm_limit,
            remark=payload.remark, created_by=actor_admin_id,
        )
        PoolAccountRepository(db).add(account)
        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="add_pool_account", resource_type="pool_account",
            resource_id=f"{pool_slug}/{payload.name}", status="success",
            after_data={"pool_slug": pool_slug, "name": payload.name, "mask": masked},
        )
        await db.commit()
        await db.refresh(account)
        return _pool_account_item(account)

    @staticmethod
    async def update_pool_account(
        db: AsyncSession, pool_slug: str, account_id: int, payload: PoolAccountUpdate, *,
        actor_admin_id: int,
    ) -> PoolAccountItem:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)
        account = await PoolAccountRepository(db).get_by_id_and_pool(account_id, pool.id)
        if account is None:
            raise NotFoundException("pool account not found")

        changed = payload.model_dump(exclude_unset=True)
        if "api_key" in changed:
            master_key = settings.PROVIDER_SECRET_MASTER_KEY
            account.api_key_enc = encrypt_api_key(changed.pop("api_key"), master_key)
            account.mask = mask_api_key(payload.api_key)
        for field, value in changed.items():
            setattr(account, field, value)
        account.updated_by = actor_admin_id

        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="update_pool_account", resource_type="pool_account",
            resource_id=f"{pool_slug}/{account_id}", status="success",
            after_data={"pool_slug": pool_slug, "account_id": account_id, "mask": account.mask},
        )
        await db.commit()
        await db.refresh(account)
        return _pool_account_item(account)

    @staticmethod
    async def disable_pool_account(
        db: AsyncSession, pool_slug: str, account_id: int, *,
        actor_admin_id: int,
    ) -> PoolAccountItem:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)
        account = await PoolAccountRepository(db).get_by_id_and_pool(account_id, pool.id)
        if account is None:
            raise NotFoundException("pool account not found")
        if account.status == PoolAccountStatus.DISABLED:
            return _pool_account_item(account)

        account.status = PoolAccountStatus.DISABLED
        account.updated_by = actor_admin_id
        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="disable_pool_account", resource_type="pool_account",
            resource_id=f"{pool_slug}/{account_id}", status="success",
            after_data={"pool_slug": pool_slug, "account_id": account_id, "status": PoolAccountStatus.DISABLED},
        )
        await db.commit()
        await db.refresh(account)
        return _pool_account_item(account)

    # ------------------------------------------------------------------
    # Routing integration
    # ------------------------------------------------------------------

    @staticmethod
    async def get_available_model_slugs(
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Return model slugs that have active pool coverage, with pool names."""
        repo = PoolRepository(db)
        pairs = await repo.get_available_model_slugs()
        grouped: dict[str, list[str]] = {}
        for slug, pool_name in pairs:
            grouped.setdefault(slug, []).append(pool_name)
        return [
            {"model_slug": slug, "pool_names": names}
            for slug, names in grouped.items()
        ]

    @staticmethod
    async def resolve_model_channels(
        db: AsyncSession, model_slugs: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Produce model_channels dict compatible with router-service format."""
        repo = PoolRepository(db)
        triples = await repo.get_active_for_routing(model_slugs)
        master_key = settings.PROVIDER_SECRET_MASTER_KEY

        result: dict[str, list[dict[str, Any]]] = {}
        for pool, pool_model, account in triples:
            enc = account.api_key_enc
            api_key = decrypt_api_key(enc["ciphertext"], enc["iv"], enc["tag"], master_key)
            entry = {
                "channel_slug": f"{pool.slug}/{account.id}",
                "provider_slug": pool.slug,
                "api_key": api_key,
                "api_base": pool.base_url,
                "upstream_model": pool_model.upstream_model_id,
                "priority": pool.priority,
                "weight": account.weight,
                "cost_input_per_million": pool_model.cost_input_per_million,
                "cost_output_per_million": pool_model.cost_output_per_million,
                "cost_cached_input_per_million": pool_model.cost_cached_input_per_million or 0,
                "pool_account_id": int(account.id),
                "rpm_limit": account.rpm_limit,
                "tpm_limit": account.tpm_limit,
            }
            result.setdefault(pool_model.model_slug, []).append(entry)
        return result

    # ------------------------------------------------------------------
    # Automation
    # ------------------------------------------------------------------

    @staticmethod
    async def sync_models(
        db: AsyncSession, pool_slug: str, *,
        actor_admin_id: int,
    ) -> SyncModelsResult:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)

        active_accounts = [a for a in (pool.accounts or []) if a.status == PoolAccountStatus.ACTIVE]
        if not active_accounts:
            raise ValidationException("pool has no active accounts to authenticate with upstream")

        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        enc = active_accounts[0].api_key_enc
        api_key = decrypt_api_key(enc["ciphertext"], enc["iv"], enc["tag"], master_key)

        client = get_internal_client(pool.base_url, timeout=30)
        resp = await client.get(
            f"{pool.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()

        body = resp.json()
        upstream_items: list[dict] = []
        for item in body.get("data", []):
            model_id = item.get("id")
            if model_id:
                upstream_items.append(item)

        model_repo = PoolModelRepository(db)
        existing_map = {m.model_slug: m for m in (pool.models or [])}
        added: list[str] = []
        existing: list[str] = []
        updated: list[str] = []

        for item in upstream_items:
            model_id = item["id"]
            if model_id in existing_map:
                existing.append(model_id)
                pm = existing_map[model_id]
                input_price, output_price = _extract_model_pricing(item)
                if pm.cost_input_per_million == 0 and input_price > 0:
                    pm.cost_input_per_million = input_price
                    updated.append(model_id)
                if pm.cost_output_per_million == 0 and output_price > 0:
                    pm.cost_output_per_million = output_price
                    if model_id not in updated:
                        updated.append(model_id)
            else:
                input_price, output_price = _extract_model_pricing(item)
                pm = PoolModel(
                    pool_id=pool.id, model_slug=model_id,
                    upstream_model_id=model_id,
                    cost_input_per_million=input_price,
                    cost_output_per_million=output_price,
                )
                model_repo.add(pm)
                added.append(model_id)

        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="sync_pool_models", resource_type="pool",
            resource_id=pool_slug, status="success",
            after_data={"added": added, "updated": updated, "existing_count": len(existing), "total_upstream": len(upstream_items)},
        )
        await db.commit()
        return SyncModelsResult(added=added, updated=updated, existing=existing, total_upstream=len(upstream_items))

    @staticmethod
    async def check_balances(
        db: AsyncSession, pool_slug: str, *,
        actor_admin_id: int,
    ) -> CheckBalancesResult:
        pool = await PoolService._get_pool_or_raise(db, pool_slug)
        if not pool.health_check_endpoint:
            raise ValidationException("pool has no health_check_endpoint configured")

        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        active_accounts = [a for a in (pool.accounts or []) if a.status in (PoolAccountStatus.ACTIVE, PoolAccountStatus.ERROR)]
        results: list[AccountBalanceResult] = []

        client = get_internal_client(pool.health_check_endpoint, timeout=30)
        for account in active_accounts:
            try:
                enc = account.api_key_enc
                api_key = decrypt_api_key(enc["ciphertext"], enc["iv"], enc["tag"], master_key)
                resp = await client.get(
                    pool.health_check_endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                body = resp.json()
                logger.info("check_balance raw response for %s: %s", account.name, body)

                balance_fen = _extract_balance(body)
                account.balance = balance_fen
                account.last_checked_at = datetime.now(UTC)
                if account.status == PoolAccountStatus.ERROR:
                    account.status = PoolAccountStatus.ACTIVE

                results.append(AccountBalanceResult(
                    account_id=account.id, name=account.name,
                    balance=balance_fen, status=account.status, error=None,
                ))
            except Exception as exc:
                account.status = PoolAccountStatus.ERROR
                account.last_checked_at = datetime.now(UTC)
                results.append(AccountBalanceResult(
                    account_id=account.id, name=account.name,
                    balance=account.balance, status=PoolAccountStatus.ERROR, error=str(exc),
                ))

        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin_id, target_admin_id=None,
            action="check_pool_balances", resource_type="pool",
            resource_id=pool_slug, status="success",
            after_data={"checked": len(results), "errors": sum(1 for r in results if r.error)},
        )
        await db.commit()
        return CheckBalancesResult(results=results)
