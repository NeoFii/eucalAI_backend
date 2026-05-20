"""ARQ worker entrypoint for api-service jobs.

Run with:  arq app.core.worker.WorkerSettings
"""

from __future__ import annotations

import app.model  # noqa: F401
from app.common.observability import configure_logging_from_settings
from app.core.config import settings
from app.core.jobs import get_worker_settings_kwargs

configure_logging_from_settings(settings)


class WorkerSettings:
    """Class consumed by `arq` CLI. Attributes are set below."""

    pass


for _key, _value in get_worker_settings_kwargs().items():
    setattr(WorkerSettings, _key, _value)
