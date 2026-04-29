"""ARQ worker entrypoint for user-service jobs."""

from __future__ import annotations

import user_service.models  # noqa: F401
from common.observability import configure_logging_from_settings
from user_service.config import settings
from user_service.jobs import get_worker_settings_kwargs

configure_logging_from_settings(settings)


class WorkerSettings:
    pass


for _key, _value in get_worker_settings_kwargs().items():
    setattr(WorkerSettings, _key, _value)
