"""Router-service configuration: gateway constants and route definitions."""

from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# Five-way route order (needed by RuntimeConfigStore for validation)
# ---------------------------------------------------------------------------
FIVEWAY_ROUTE_ORDER: List[str] = ["纠错", "工具调用", "通用任务", "任务拆解", "编程"]
FIVEWAY_DEFAULT_WEIGHTS: Dict[str, float] = {
    "纠错": 1.0,
    "工具调用": 1.0,
    "通用任务": 1.0,
    "任务拆解": 1.0,
    "编程": 1.0,
}

# ---------------------------------------------------------------------------
# Default service settings
# ---------------------------------------------------------------------------
DEFAULT_SERVICE_HOST = "0.0.0.0"
DEFAULT_SERVICE_PORT = 8013
DEFAULT_ROUTER_ALIAS = "auto"
