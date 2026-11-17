import enum
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """Always hands out timezone-aware UTC datetimes, on PostgreSQL and SQLite alike."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use UTC-aware values")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


class EssayStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    essays: Mapped[list["Essay"]] = relationship(back_populates="user")


class Essay(Base):
    """One grading attempt. Only COMPLETED rows are shown in the history."""

    __tablename__ = "essays"
    __table_args__ = (Index("ix_essays_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[EssayStatus] = mapped_column(
        Enum(EssayStatus, name="essay_status", values_callable=lambda e: [m.value for m in e]),
        default=EssayStatus.PENDING,
    )
    question: Mapped[str] = mapped_column(Text)
    essay_text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(SmallInteger)
    feedback_language: Mapped[str] = mapped_column(String(8), default="vi")

    task_response: Mapped[int | None] = mapped_column(SmallInteger)
    coherence_cohesion: Mapped[int | None] = mapped_column(SmallInteger)
    lexical_resource: Mapped[int | None] = mapped_column(SmallInteger)
    grammatical_range_accuracy: Mapped[int | None] = mapped_column(SmallInteger)
    overall_band: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))

    # {"task_response": {"comment": "...", "errors": [{"quote", "issue", "correction"}]}, ...}
    feedback: Mapped[dict | None] = mapped_column(JsonType)
    # [{"original", "improved", "explanation"}]
    rewrites: Mapped[list | None] = mapped_column(JsonType)

    provider: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    user: Mapped[User] = relationship(back_populates="essays")
