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


def register_relay_resources(registry: LifespanRegistry) -> None:
    """Register relay-core singletons with the lifespan registry.

    Priority ordering:
      - routing_config_cache at 20 (must load before routing can work)
      - inference_client at 25
      - channel_selector at 25
      - channel_affinity at 25
      - sdk_client_pool at 25
      - rate_limiter at 25
    """
    from app.common.infra.cache import get_cache_redis
    from app.core.config import settings
    from app.core.db import get_db_context
    from app.relay.channel_affinity import ChannelAffinityStore
    from app.relay.channel_selector import ChannelSelector
    from app.relay.config_cache import RoutingConfigCache
    from app.relay.dependencies import init_relay_globals, shutdown_relay
    from app.relay.inference_client import InferenceClient
    from app.relay.rate_limiter import RateLimiter
    from app.relay.sdk_clients import SdkClientPool

    # Shared state for init/shutdown closures
    _state: dict = {}

    async def _init_relay() -> None:
        cache_redis = get_cache_redis()

        # 1. RoutingConfigCache (priority=20 — must succeed, D-12)
        config_cache = RoutingConfigCache(cache_redis)
        from app.common.infra.db.runtime import ServiceDatabaseRuntime
        from app.core.db import _runtime
        session_factory = _runtime._session_factory
        if session_factory is None:
            raise RuntimeError("DB session factory not initialized before relay startup")
        await config_cache.start(session_factory)

        # 2. InferenceClient
        inference_client = InferenceClient(
            base_url=settings.INFERENCE_SERVICE_URL,
            secret=settings.INFERENCE_SERVICE_SECRET,
        )

        # 3. ChannelSelector
        channel_selector = ChannelSelector(
            cooldown_seconds=settings.CHANNEL_COOLDOWN_SECONDS,
            auto_disable_enabled=settings.CHANNEL_AUTO_DISABLE_ENABLED,
            auto_disable_threshold=settings.CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD,
        )

        # 4. ChannelAffinityStore
        affinity_redis = cache_redis if settings.CHANNEL_AFFINITY_ENABLED else None
        affinity_store = ChannelAffinityStore(
            redis=affinity_redis,
            ttl=settings.CHANNEL_AFFINITY_TTL,
        )

        # 5. SdkClientPool
        sdk_client_pool = SdkClientPool(max_size=settings.SDK_CLIENT_POOL_MAX_SIZE)
        _state["sdk_client_pool"] = sdk_client_pool

        # 6. RateLimiter
        rate_limiter = RateLimiter(
            redis=cache_redis,
            default_user_rpm=settings.RATE_LIMIT_DEFAULT_USER_RPM,
            global_rpm=settings.RATE_LIMIT_GLOBAL_RPM,
        )

        # Wire all singletons
        init_relay_globals(
            config_cache=config_cache,
            inference_client=inference_client,
            channel_selector=channel_selector,
            affinity_store=affinity_store,
            sdk_client_pool=sdk_client_pool,
            rate_limiter=rate_limiter,
        )
        _state["initialized"] = True

    async def _shutdown_relay() -> None:
        await shutdown_relay()

    registry.register(
        name="relay_core",
        init_fn=_init_relay,
        shutdown_fn=_shutdown_relay,
        priority=20,
    )
