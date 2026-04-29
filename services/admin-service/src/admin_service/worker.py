"""ARQ worker entrypoint for admin-service jobs."""

from __future__ import annotations

import admin_service.models  # noqa: F401
from common.observability import configure_logging_from_settings
from admin_service.config import settings
from admin_service.jobs import get_worker_settings_kwargs

configure_logging_from_settings(settings)


class WorkerSettings:
    pass


for _key, _value in get_worker_settings_kwargs().items():
    setattr(WorkerSettings, _key, _value)
