"""Smart router model selection helpers."""

from __future__ import annotations

from dataclasses import dataclass

import litellm
from sqlalchemy.ext.asyncio import AsyncSession

from router_service.config import get_settings
from router_service.services.testing_catalog_client import TestingCatalogClientService


@dataclass
class DifficultyDecision:
    """Difficulty classification result."""

    difficulty: int
    source: str


class SmartRouterService:
    """Resolve smart-router alias into a concrete logical model."""

    @staticmethod
    async def classify(messages: list[dict]) -> DifficultyDecision:
        settings = get_settings()
        classifier_model = settings.SMART_ROUTER_CLASSIFIER_MODEL.strip()
        if classifier_model:
            try:
                response = await litellm.acompletion(
                    model=classifier_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You classify request difficulty from 1 to 5. "
                                "Reply with exactly one digit."
                            ),
                        },
                        {
                            "role": "user",
                            "content": "\n".join(
                                str(item.get("content", ""))
                                for item in messages
                                if isinstance(item, dict)
                            ),
                        },
                    ],
                    temperature=settings.SMART_ROUTER_CLASSIFIER_TEMPERATURE,
                    timeout=settings.SMART_ROUTER_CLASSIFIER_TIMEOUT_SECONDS,
                    max_tokens=settings.SMART_ROUTER_CLASSIFIER_MAX_TOKENS,
                )
                content = (
                    response.choices[0].message.content
                    if getattr(response, "choices", None)
                    else ""
                )
                difficulty = int(str(content).strip()[0])
                return DifficultyDecision(difficulty=max(1, min(5, difficulty)), source="llm")
            except Exception:
                pass
        return DifficultyDecision(difficulty=SmartRouterService._heuristic(messages), source="heuristic")

    @staticmethod
    def _heuristic(messages: list[dict]) -> int:
        text = "\n".join(str(item.get("content", "")) for item in messages if isinstance(item, dict)).lower()
        score = 1
        for needle in ("optimize", "architecture", "algorithm", "benchmark", "distributed", "璇佹槑", "鎺ㄧ悊"):
            if needle.lower() in text:
                score += 1
        return max(1, min(5, score))

    @staticmethod
    async def resolve_model(db: AsyncSession, messages: list[dict]) -> tuple[str, DifficultyDecision]:
        settings = get_settings()
        decision = await SmartRouterService.classify(messages)
        mapped = settings.smart_router_difficulty_model_map.get(decision.difficulty)
        if mapped:
            return mapped, decision

        ranked = await SmartRouterService._load_ranked_model_slugs(db)
        if ranked:
            if len(ranked) == 1:
                return ranked[0], decision
            index = round(((decision.difficulty - 1) / 4) * (len(ranked) - 1))
            return ranked[index], decision

        fallback = settings.SMART_ROUTER_FALLBACK_MODEL.strip()
        if fallback:
            return fallback, decision
        raise ValueError("smart-router has no available target model")

    @staticmethod
    async def _load_ranked_model_slugs(db: AsyncSession) -> list[str]:
        del db
        payload = await TestingCatalogClientService.list_models()
        return list(payload.get("ranked_logical_models") or [])
