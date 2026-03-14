"""Model and provider route resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from router_service.services.testing_catalog_client import TestingCatalogClientService


@dataclass
class RouteCandidate:
    """A single provider route candidate."""

    provider_slug: str
    provider_name: str
    provider_model_name: str
    api_base_url: str
    encrypted_api_key: tuple[str, str, str]
    input_price_per_m: float | None
    output_price_per_m: float | None

    @property
    def price_score(self) -> float:
        if self.input_price_per_m is None or self.output_price_per_m is None:
            return math.inf
        return self.input_price_per_m + self.output_price_per_m


class RoutingService:
    """Resolve route candidates from testing_service domain tables."""

    @staticmethod
    def split_provider_prefix(model_name: str) -> tuple[str | None, str]:
        if ":" in model_name:
            prefix, remainder = model_name.split(":", 1)
            prefix = prefix.strip().lower()
            remainder = remainder.strip()
            if prefix and remainder:
                return prefix, remainder
        return None, model_name

    @staticmethod
    async def build_candidates(
        db: AsyncSession,
        *,
        model_name: str,
        provider_hint: str | None = None,
    ) -> list[RouteCandidate]:
        del db
        payload = await TestingCatalogClientService.resolve_routes(
            model_name=model_name,
            provider_hint=provider_hint,
        )
        candidates: list[RouteCandidate] = []
        for item in payload["items"]:
            candidates.append(
                RouteCandidate(
                    provider_slug=item["provider_slug"],
                    provider_name=item["provider_name"],
                    provider_model_name=item["provider_model_name"],
                    api_base_url=item["api_base_url"],
                    encrypted_api_key=(
                        item["encrypted_api_key"]["ciphertext"],
                        item["encrypted_api_key"]["iv"],
                        item["encrypted_api_key"]["tag"],
                    ),
                    input_price_per_m=item["input_price_per_m"],
                    output_price_per_m=item["output_price_per_m"],
                )
            )
        candidates.sort(key=lambda item: (item.price_score, item.provider_slug))
        return candidates

    @staticmethod
    async def list_available_models(db: AsyncSession) -> list[dict[str, str]]:
        del db
        payload = await TestingCatalogClientService.list_models()
        return payload["items"]
