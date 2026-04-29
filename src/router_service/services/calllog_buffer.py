"""In-memory call-log buffer with periodic batch flush to user-service."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from router_service.settings import RouterSettings

logger = logging.getLogger("router_service.calllog_buffer")


@dataclass
class PendingLogEntry:
    request_id: str
    fields: dict[str, Any]
    has_billing: bool = False
    created_at: float = field(default_factory=time.monotonic)
    retry_count: int = 0


class CallLogBuffer:

    def __init__(
        self,
        *,
        settings: RouterSettings,
        flush_interval: float = 5.0,
        max_buffer: int = 10000,
        max_retries: int = 3,
    ) -> None:
        self._settings = settings
        self._flush_interval = flush_interval
        self._max_buffer = max_buffer
        self._max_retries = max_retries
        self._lock = asyncio.Lock()
        self._entries: dict[str, PendingLogEntry] = {}
        self._task: asyncio.Task | None = None

    async def record(self, request_id: str, **fields: Any) -> None:
        async with self._lock:
            if len(self._entries) >= self._max_buffer:
                logger.warning("call-log buffer full (%d), dropping oldest entry", self._max_buffer)
                oldest_key = next(iter(self._entries))
                del self._entries[oldest_key]
            self._entries[request_id] = PendingLogEntry(
                request_id=request_id,
                fields=fields,
            )

    async def update(self, request_id: str, **fields: Any) -> None:
        async with self._lock:
            entry = self._entries.get(request_id)
            if entry is None:
                entry = PendingLogEntry(request_id=request_id, fields={})
                self._entries[request_id] = entry
            entry.fields.update(fields)
            cost = fields.get("cost", entry.fields.get("cost", 0))
            status = fields.get("status", entry.fields.get("status"))
            if cost and cost > 0 and status == 1:
                entry.has_billing = True

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        logger.info("call-log buffer started (flush_interval=%.1fs)", self._flush_interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("call-log buffer stopped, final flush complete")

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._flush_interval)
                try:
                    await self._flush()
                except Exception:
                    logger.warning("call-log flush failed", exc_info=True)
        except asyncio.CancelledError:
            return

    async def _flush(self) -> None:
        async with self._lock:
            if not self._entries:
                return
            batch = self._entries
            self._entries = {}

        entries_list = []
        for entry in batch.values():
            action = "complete" if entry.has_billing else "create"
            if "status" not in entry.fields:
                action = "create"
            elif entry.fields.get("status") in (1, 2, 4) and not entry.has_billing:
                action = "update"
            entries_list.append({
                "request_id": entry.request_id,
                "action": action,
                **entry.fields,
            })

        from router_service.gateway_calllog_batch import BatchCallLogGateway

        ok = await BatchCallLogGateway.flush_batch(
            settings=self._settings,
            entries=entries_list,
        )
        if not ok:
            async with self._lock:
                for entry in batch.values():
                    entry.retry_count += 1
                    if entry.retry_count <= self._max_retries:
                        if entry.request_id not in self._entries:
                            self._entries[entry.request_id] = entry
                    else:
                        logger.warning(
                            "call-log entry %s dropped after %d retries",
                            entry.request_id, entry.retry_count,
                        )
