"""Invitation-release outbox repository."""

from __future__ import annotations

from common.db import BaseRepository
from user_service.models import InvitationReleaseOutbox


class InvitationReleaseOutboxRepository(BaseRepository[InvitationReleaseOutbox]):
    """Repository for invitation release compensation records."""

    def __init__(self, session) -> None:
        super().__init__(session, InvitationReleaseOutbox)
