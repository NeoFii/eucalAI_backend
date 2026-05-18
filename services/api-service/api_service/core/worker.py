"""ARQ worker entrypoint for api-service jobs.

Run with:  arq api_service.core.worker.WorkerSettings
"""

from __future__ import annotations

import api_service.models  # noqa: F401  — import models so SQLAlchemy registers them
from api_service.common.observability import configure_logging_from_settings
from api_service.core.config import settings
from api_service.core.jobs import get_worker_settings_kwargs

configure_logging_from_settings(settings)


class WorkerSettings:
    """Class consumed by `arq` CLI. Attributes are set below."""

    pass


for _key, _value in get_worker_settings_kwargs().items():
    setattr(WorkerSettings, _key, _value)
