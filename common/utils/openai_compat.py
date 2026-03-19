"""Helpers for OpenAI-compatible upstream configuration."""

from __future__ import annotations


CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


def normalize_openai_compatible_base_url(url: str | None) -> str | None:
    """Accept either a base URL or a full chat-completions endpoint."""
    if url is None:
        return None

    normalized = url.strip().rstrip("/")
    if not normalized:
        return None

    if normalized.lower().endswith(CHAT_COMPLETIONS_SUFFIX):
        normalized = normalized[: -len(CHAT_COMPLETIONS_SUFFIX)].rstrip("/")
    return normalized or None
