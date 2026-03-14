# -*- coding: utf-8 -*-
"""ARQ worker entrypoint for benchmark jobs."""

from __future__ import annotations

import testing_service.models  # noqa: F401

from testing_service.benchmark.jobs import get_worker_settings_kwargs


class WorkerSettings:
    pass


for _key, _value in get_worker_settings_kwargs().items():
    setattr(WorkerSettings, _key, _value)
