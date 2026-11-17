"""users and essays

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models import UTCDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
essay_status = sa.Enum("pending", "completed", "failed", name="essay_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "essays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", essay_status, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("essay_text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.SmallInteger(), nullable=False),
        sa.Column("feedback_language", sa.String(8), nullable=False),
        sa.Column("task_response", sa.SmallInteger(), nullable=True),
        sa.Column("coherence_cohesion", sa.SmallInteger(), nullable=True),
        sa.Column("lexical_resource", sa.SmallInteger(), nullable=True),
        sa.Column("grammatical_range_accuracy", sa.SmallInteger(), nullable=True),
        sa.Column("overall_band", sa.Numeric(2, 1), nullable=True),
        sa.Column("feedback", json_type, nullable=True),
        sa.Column("rewrites", json_type, nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("completed_at", UTCDateTime(), nullable=True),
    )
    op.create_index("ix_essays_created_at", "essays", ["created_at"])
    op.create_index("ix_essays_user_created", "essays", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("essays")
    op.drop_table("users")
    essay_status.drop(op.get_bind(), checkfirst=True)
