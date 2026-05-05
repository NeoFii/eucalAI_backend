"""Best-effort gateway for writing API call logs — delegates to in-memory buffer."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from services.calllog_buffer import CallLogBuffer

logger = logging.getLogger("router_service.calllog")


class CallLogGateway:

    def __init__(self, buffer: "CallLogBuffer | None") -> None:
        self._buffer = buffer

    async def create_call_log(self, **fields: Any) -> dict | None:
        if self._buffer is None:
            logger.warning("call-log buffer not initialized, dropping create for %s", fields.get("request_id"))
            return None
        request_id = fields.pop("request_id", None)
        if not request_id:
            return None
        await self._buffer.record(request_id, **fields)
        return {"request_id": request_id}

    async def update_call_log(
        self, *, request_id: str, **fields: Any
    ) -> dict | None:
        if self._buffer is None:
            logger.warning("call-log buffer not initialized, dropping update for %s", request_id)
            return None
        await self._buffer.update(request_id, **fields)
        return {"request_id": request_id}
