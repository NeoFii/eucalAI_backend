"""Backend-app: consolidated FastAPI process for admin + user + content + testing domains.

router-service stays independent for horizontal scaling; testing-scheduler and
testing-worker remain separate background processes. This module is the single
entrypoint for all low-QPS management traffic.
"""
