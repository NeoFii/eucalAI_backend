"""Internal router-catalog endpoints for router-service."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.internal import build_internal_auth_dependency
from testing_service.dependencies import get_db_session
from testing_service.config import get_settings
from testing_service.models import Model, ModelProviderOffering, Provider

settings = get_settings()
router = APIRouter(prefix="/internal/router", tags=["internal-router"])
verify_internal_secret = build_internal_auth_dependency(
    settings.internal_secret,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"router-service"},
)


class ResolveRoutesRequest(BaseModel):
    """Resolve route candidates for router-service."""

    model_name: str
    provider_hint: str | None = None


def _serialize_candidate(offering: ModelProviderOffering, provider: Provider) -> dict:
    api_base_url = provider.probe_api_base_url or offering.api_base_url
    return {
        "offering_id": int(offering.id),
        "model_id": int(offering.model_id),
        "provider_id": int(provider.id),
        "provider_slug": provider.slug,
        "provider_name": provider.name,
        "provider_model_name": (offering.provider_model_name or "").strip(),
        "api_base_url": api_base_url.rstrip("/") if api_base_url else "",
        "encrypted_api_key": {
            "ciphertext": provider.probe_api_key_ciphertext,
            "iv": provider.probe_api_key_iv,
            "tag": provider.probe_api_key_tag,
        },
        "input_price_per_m": float(offering.price_input_per_m) if offering.price_input_per_m is not None else None,
        "output_price_per_m": float(offering.price_output_per_m) if offering.price_output_per_m is not None else None,
    }


@router.get("/models")
async def list_router_models(
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Model.slug, ModelProviderOffering.provider_model_name, ModelProviderOffering, Provider)
        .join(ModelProviderOffering, ModelProviderOffering.model_id == Model.id)
        .join(Provider, ModelProviderOffering.provider_id == Provider.id)
        .where(Model.is_active.is_(True))
        .where(Provider.is_active.is_(True))
        .where(ModelProviderOffering.is_active.is_(True))
        .where(ModelProviderOffering.deleted_at.is_(None))
        .where(Provider.deleted_at.is_(None))
        .where(ModelProviderOffering.provider_model_name.is_not(None))
    )
    rows = (await db.execute(stmt)).all()

    seen: set[str] = set()
    aggregates: dict[str, list[float | int | bool]] = defaultdict(lambda: [0.0, 0, False])
    for model_slug, provider_model_name, offering, provider in rows:
        api_base_url = provider.probe_api_base_url or offering.api_base_url
        has_key = bool(
            provider.probe_api_key_ciphertext
            and provider.probe_api_key_iv
            and provider.probe_api_key_tag
        )
        if not api_base_url or not has_key:
            continue

        if model_slug:
            seen.add(model_slug)
            total, count, has_unknown = aggregates[model_slug]
            if offering.price_input_per_m is None or offering.price_output_per_m is None:
                aggregates[model_slug] = [total, count, True]
            else:
                total += float(offering.price_input_per_m + offering.price_output_per_m)
                count += 1
                aggregates[model_slug] = [total, count, has_unknown]

        if provider_model_name:
            seen.add(f"{provider.slug}:{provider_model_name}")

    priced = []
    fallback = []
    for slug, (total, count, has_unknown) in aggregates.items():
        if count > 0:
            priced.append((slug, total / count))
        elif has_unknown:
            fallback.append(slug)
    priced.sort(key=lambda item: (item[1], item[0]))
    fallback.sort()

    return {
        "items": [
            {"id": item, "object": "model", "owned_by": "eucal-router"}
            for item in sorted(seen)
        ],
        "ranked_logical_models": [slug for slug, _ in priced] + fallback,
    }


@router.post("/routes/resolve")
async def resolve_routes(
    payload: ResolveRoutesRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(ModelProviderOffering, Provider, Model)
        .join(Provider, ModelProviderOffering.provider_id == Provider.id)
        .join(Model, ModelProviderOffering.model_id == Model.id)
        .where(Model.is_active.is_(True))
        .where(Provider.is_active.is_(True))
        .where(ModelProviderOffering.is_active.is_(True))
        .where(ModelProviderOffering.deleted_at.is_(None))
        .where(Provider.deleted_at.is_(None))
        .where(ModelProviderOffering.provider_model_name.is_not(None))
        .where(
            or_(
                Model.slug == payload.model_name,
                ModelProviderOffering.provider_model_name == payload.model_name,
            )
        )
    )
    if payload.provider_hint:
        stmt = stmt.where(Provider.slug == payload.provider_hint)

    rows = (await db.execute(stmt)).all()
    candidates = []
    for offering, provider, _model in rows:
        api_base_url = provider.probe_api_base_url or offering.api_base_url
        if not api_base_url:
            continue
        if (
            not provider.probe_api_key_ciphertext
            or not provider.probe_api_key_iv
            or not provider.probe_api_key_tag
        ):
            continue
        provider_model_name = (offering.provider_model_name or "").strip()
        if not provider_model_name:
            continue
        candidates.append(_serialize_candidate(offering, provider))

    candidates.sort(
        key=lambda item: (
            float("inf")
            if item["input_price_per_m"] is None or item["output_price_per_m"] is None
            else item["input_price_per_m"] + item["output_price_per_m"],
            item["provider_slug"],
        )
    )
    return {"items": candidates}


@router.get("/offerings/{offering_id}")
async def get_router_offering(
    offering_id: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(ModelProviderOffering, Provider, Model)
        .join(Provider, ModelProviderOffering.provider_id == Provider.id)
        .join(Model, ModelProviderOffering.model_id == Model.id)
        .where(ModelProviderOffering.id == offering_id)
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="offering not found")
    offering, provider, model = row
    payload = _serialize_candidate(offering, provider)
    payload["model_slug"] = model.slug
    payload["model_name"] = model.name
    return payload
