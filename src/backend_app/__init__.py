"""Backend-app: consolidated FastAPI process for admin + user domains.

router-service stays independent for horizontal scaling. This module is the
single entrypoint for all low-QPS management traffic.
"""
