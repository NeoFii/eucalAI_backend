"""LifespanRegistry — ordered resource initialization and teardown."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class _Resource:
    """A managed lifecycle resource."""

    name: str
    init_fn: Callable[[], Awaitable[None]]
    shutdown_fn: Callable[[], Awaitable[None]] | None
    priority: int


@dataclass
class LifespanRegistry:
    """Registry that manages ordered startup/shutdown of async resources.

    Resources are initialized in ascending priority order and shut down in
    descending priority order.  If any resource fails during startup, all
    previously initialized resources are cleaned up before the error propagates
    (fail-fast strategy).
    """

    _resources: list[_Resource] = field(default_factory=list)
    _initialized: list[str] = field(default_factory=list)

    def register(
        self,
        name: str,
        init_fn: Callable[[], Awaitable[None]],
        shutdown_fn: Callable[[], Awaitable[None]] | None = None,
        priority: int = 100,
    ) -> None:
        """Register a resource for lifecycle management.

        Args:
            name: Human-readable resource identifier.
            init_fn: Async callable invoked during startup.
            shutdown_fn: Optional async callable invoked during shutdown.
            priority: Lower values initialize first, shut down last.
        """
        self._resources.append(
            _Resource(name=name, init_fn=init_fn, shutdown_fn=shutdown_fn, priority=priority)
        )

    async def startup(self) -> None:
        """Initialize all resources in priority order (ascending).

        On failure, cleans up already-initialized resources and re-raises.
        """
        ordered = sorted(self._resources, key=lambda r: r.priority)
        for resource in ordered:
            try:
                await resource.init_fn()
                self._initialized.append(resource.name)
                logger.info("resource_initialized", extra={"resource": resource.name})
            except Exception:
                logger.critical(
                    "resource_init_failed",
                    extra={"resource": resource.name},
                    exc_info=True,
                )
                await self._cleanup()
                raise

    async def shutdown(self) -> None:
        """Shut down all initialized resources in reverse priority order."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Shut down initialized resources in descending priority order."""
        # Build lookup of initialized resources
        initialized_set = set(self._initialized)
        ordered = sorted(
            (r for r in self._resources if r.name in initialized_set),
            key=lambda r: r.priority,
            reverse=True,
        )
        for resource in ordered:
            if resource.shutdown_fn is None:
                continue
            try:
                await resource.shutdown_fn()
            except Exception:
                logger.warning(
                    "resource_shutdown_failed",
                    extra={"resource": resource.name},
                    exc_info=True,
                )
        self._initialized.clear()
