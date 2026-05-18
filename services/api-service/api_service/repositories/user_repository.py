"""User repository — merges user, session, and email verification code access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import cast, func, or_, select, Date

from api_service.common.infra.db.repository import BaseRepository
from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.common.utils.timezone import now
from api_service.models import User, UserSession, EmailVerificationCode


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session, User)

    # ──────────────────────────────────────────────
    # User methods
    # ──────────────────────────────────────────────

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    async def get_by_uid(self, uid: str) -> User | None:
        return (await self.session.execute(select(User).where(User.uid == uid))).scalar_one_or_none()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)

    async def get_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: int | None = None,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        if search:
            search_value = search.strip()
            if search_value:
                escaped = _escape_like(search_value)
                stmt = stmt.where(
                    or_(
                        User.uid == search_value,
                        User.uid.like(f"{escaped}%", escape="\\"),
                        User.email.like(f"%{escaped}%", escape="\\"),
                    )
                )
        if status is not None:
            stmt = stmt.where(User.status == status)
        stmt = stmt.order_by(User.created_at.desc(), User.id.desc())
        total = int(
            (await self.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
            or 0
        )
        rows = await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        return list(rows.scalars().all()), total

    def add(self, user: User) -> None:
        self.session.add(user)

    async def update_rpm_limit(self, user_id: int, rpm_limit: int | None) -> User | None:
        """Set or clear the per-user RPM override (NULL = use global default)."""
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.rpm_limit = rpm_limit
        return user

    async def get_daily_registrations(
        self, *, start: datetime, end: datetime,
    ) -> list[dict]:
        reg_date = cast(User.created_at, Date).label("reg_date")
        query = (
            select(reg_date, func.count().label("count"))
            .where(User.created_at >= start, User.created_at < end)
            .group_by(reg_date)
            .order_by(reg_date.asc())
        )
        rows = (await self.session.execute(query)).all()
        return [{"date": str(r.reg_date), "count": int(r.count)} for r in rows]

    async def count_since(self, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= since)
        )
        return int(result.scalar() or 0)

    async def count_in_range(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        statement = select(func.count(User.id))
        if start is not None:
            statement = statement.where(User.created_at >= start)
        if end is not None:
            statement = statement.where(User.created_at < end)
        result = await self.session.execute(statement)
        return int(result.scalar() or 0)

    # ──────────────────────────────────────────────
    # Session methods (prefixed with session_)
    # ──────────────────────────────────────────────

    async def get_session_by_token_jti(self, token_jti: str) -> UserSession | None:
        return (
            await self.session.execute(select(UserSession).where(UserSession.token_jti == token_jti))
        ).scalar_one_or_none()

    async def list_active_sessions_for_user(self, user_id: int) -> list[UserSession]:
        result = await self.session.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        return list(result.scalars().all())

    def add_session(self, session_obj: UserSession) -> None:
        self.session.add(session_obj)

    def revoke_session(self, session_obj: UserSession) -> None:
        session_obj.revoked_at = now()

    # ──────────────────────────────────────────────
    # EmailCode methods (prefixed with email_code_)
    # ──────────────────────────────────────────────

    async def email_code_count_created_since(
        self, email: str, purpose: str, created_at_gte: datetime,
    ) -> int:
        statement = select(func.count()).select_from(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.created_at >= created_at_gte,
        )
        return int((await self.session.execute(statement)).scalar() or 0)

    async def email_code_latest_for_email(
        self, email: str, purpose: str,
    ) -> EmailVerificationCode | None:
        statement = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def email_code_latest_unused_for_email(
        self, email: str, purpose: str, *, for_update: bool = False,
    ) -> EmailVerificationCode | None:
        statement = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.used_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def email_code_list_unused_for_email(
        self, email: str, purpose: str,
    ) -> list[EmailVerificationCode]:
        statement = select(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used_at.is_(None),
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def email_code_delete(self, record: EmailVerificationCode) -> None:
        await self.session.delete(record)

    def email_code_add(self, record: EmailVerificationCode) -> None:
        self.session.add(record)
