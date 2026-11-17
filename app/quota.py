"""Daily limits.

- Per user: COMPLETED attempts plus attempts still in progress count. Failed attempts
  (provider down, malformed answer) do not, so users are never charged for our errors.
- Whole system: EVERY attempt that reached the AI provider counts, failed or not,
  because the money is spent either way. This is the cost guard.

Reservation happens in one transaction under a PostgreSQL advisory lock, so two
parallel requests cannot both take the last slot.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Essay, EssayStatus, User, utcnow

# A pending attempt older than this is treated as dead (e.g. the server restarted).
PENDING_TTL = timedelta(minutes=10)
_LOCK_KEY = 74_201_117  # arbitrary constant for pg_advisory_xact_lock


class QuotaExceeded(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class DayWindow:
    start: datetime
    end: datetime


def current_day(settings: Settings, now: datetime | None = None) -> DayWindow:
    tz = ZoneInfo(settings.quota_timezone)
    local = (now or utcnow()).astimezone(tz)
    start = datetime.combine(local.date(), time.min, tzinfo=tz)
    return DayWindow(start=start, end=start + timedelta(days=1))


async def user_used(session: AsyncSession, user_id: int, day: DayWindow) -> int:
    now = utcnow()
    stmt = select(func.count(Essay.id)).where(
        Essay.user_id == user_id,
        Essay.created_at >= day.start,
        Essay.created_at < day.end,
        or_(
            Essay.status == EssayStatus.COMPLETED,
            (Essay.status == EssayStatus.PENDING) & (Essay.created_at >= now - PENDING_TTL),
        ),
    )
    return (await session.execute(stmt)).scalar_one()


async def global_used(session: AsyncSession, day: DayWindow) -> int:
    stmt = select(func.count(Essay.id)).where(
        Essay.created_at >= day.start, Essay.created_at < day.end
    )
    return (await session.execute(stmt)).scalar_one()


async def reserve_attempt(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    question: str,
    essay_text: str,
    word_count: int,
    language: str,
    provider: str,
    model: str,
) -> Essay:
    """Check both limits and insert a PENDING essay atomically."""
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})

    day = current_day(settings)
    if await global_used(session, day) >= settings.global_daily_limit:
        await session.rollback()
        raise QuotaExceeded(
            "The service has used up today's grading budget. Please try again tomorrow."
        )
    if await user_used(session, user.id, day) >= settings.user_daily_limit:
        await session.rollback()
        raise QuotaExceeded(
            f"Daily limit reached: {settings.user_daily_limit} essays per day. "
            f"It resets at {day.end.strftime('%H:%M')} ({settings.quota_timezone})."
        )

    essay = Essay(
        user_id=user.id,
        status=EssayStatus.PENDING,
        question=question,
        essay_text=essay_text,
        word_count=word_count,
        feedback_language=language,
        provider=provider,
        model_name=model,
    )
    session.add(essay)
    await session.commit()  # releases the advisory lock
    return essay
