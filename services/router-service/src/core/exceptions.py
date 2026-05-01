"""Router-service domain exceptions."""

from __future__ import annotations

import re

from fastapi import HTTPException


class RoutingError(HTTPException):
    """HTTPException subclass carrying a stable error_code for call-log recording."""

    def __init__(self, status_code: int, *, error_code: str, detail: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


_SENSITIVE_RE = re.compile(
    r"((?:key|token|secret|password|auth)[=:]\S{0,60}|https?://\S+)",
    re.IGNORECASE,
)


def sanitize_error(exc: Exception, max_len: int = 200) -> str:
    raw = str(exc)[:max_len]
    return _SENSITIVE_RE.sub("[REDACTED]", raw)
