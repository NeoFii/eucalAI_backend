"""Minimal shared repository base."""

from __future__ import annotations

from typing import Generic, TypeVar

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Store the session and model class for derived repositories."""

    def __init__(self, session, model: type[ModelT] | None = None) -> None:
        self.session = session
        self.model = model
