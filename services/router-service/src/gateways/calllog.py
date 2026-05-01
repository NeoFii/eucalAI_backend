"""Best-effort gateway for writing API call logs — delegates to in-memory buffer."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("router_service.calllog")


class CallLogGateway:

    @staticmethod
    async def create_call_log(*, settings: Any, **fields: Any) -> dict | None:
        from core.dependencies import get_calllog_buffer

        buf = get_calllog_buffer()
        if buf is None:
            logger.warning("call-log buffer not initialized, dropping create for %s", fields.get("request_id"))
            return None
        request_id = fields.pop("request_id", None)
        if not request_id:
            return None
        await buf.record(request_id, **fields)
        return {"request_id": request_id}

    @staticmethod
    async def update_call_log(
        *, settings: Any, request_id: str, **fields: Any
    ) -> dict | None:
        from core.dependencies import get_calllog_buffer

        buf = get_calllog_buffer()
        if buf is None:
            logger.warning("call-log buffer not initialized, dropping update for %s", request_id)
            return None
        await buf.update(request_id, **fields)
        return {"request_id": request_id}
