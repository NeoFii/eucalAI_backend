"""Text processing utilities: truncation, stringify."""

from __future__ import annotations

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
