"""Minimal shared gateway base class."""

from __future__ import annotations


class BaseGateway:
    """Base gateway storing the remote service identity."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
