"""Text processing utilities: truncation, stringify."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def truncate_text(text: Any, max_chars: int = 2000) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False)
        except Exception:
            text = str(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " ..."


def stringify_message_content(msg: Any) -> str:
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        parts = []
        for x in msg:
            if isinstance(x, dict) and "text" in x:
                parts.append(str(x.get("text", "")))
            else:
                parts.append(stringify_message_content(x))
        return " ".join([p for p in parts if p])
    if isinstance(msg, dict):
        if "content" in msg and isinstance(msg["content"], str):
            return msg["content"]
        try:
            return json.dumps(msg, ensure_ascii=False)
        except Exception:
            return str(msg)
    return str(msg)


def compute_input_hash(messages: list[dict]) -> str:
    """sha256(canonical JSON of messages)[:32].

    Used by route-monitor's "compare/replay" view to group requests by identical
    input. Sort keys are enabled so message dicts with same content but different
    key ordering still hash equally.
    """
    try:
        canon = json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        canon = str(messages)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]
