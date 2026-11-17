import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MIN_WORDS = 150
MAX_WORDS = 600

CRITERIA = (
    "task_response",
    "coherence_cohesion",
    "lexical_resource",
    "grammatical_range_accuracy",
)
Criterion = Literal[
    "task_response",
    "coherence_cohesion",
    "lexical_resource",
    "grammatical_range_accuracy",
]

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


# ---------- Auth ----------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


# ---------- Grading request ----------


class GradeIn(BaseModel):
    question: str = Field(min_length=20, max_length=2000)
    essay: str = Field(max_length=6000)
    feedback_language: Literal["vi", "en"] = "vi"

    @field_validator("question", "essay")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("essay")
    @classmethod
    def check_length(cls, v: str) -> str:
        words = count_words(v)
        if not MIN_WORDS <= words <= MAX_WORDS:
            raise ValueError(f"Essay must be {MIN_WORDS}-{MAX_WORDS} words (currently {words})")
        return v


# ---------- What the model must return (validated before anything is saved) ----------

Band = Annotated[int, Field(ge=0, le=9)]


class CriterionBands(BaseModel):
    """IELTS examiners award whole bands per criterion (public band descriptors are 0-9)."""

    task_response: Band
    coherence_cohesion: Band
    lexical_resource: Band
    grammatical_range_accuracy: Band


class QuotedError(BaseModel):
    criterion: Criterion
    quote: str = Field(min_length=1, max_length=400)
    issue: str = Field(min_length=1, max_length=600)
    correction: str | None = Field(default=None, max_length=600)


class Rewrite(BaseModel):
    original: str = Field(min_length=1, max_length=600)
    improved: str = Field(min_length=1, max_length=800)
    explanation: str = Field(default="", max_length=600)


class ModelVerdict(BaseModel):
    bands: CriterionBands
    errors: list[QuotedError] = Field(default_factory=list, max_length=40)
    rewrites: list[Rewrite] = Field(min_length=3, max_length=5)

    @field_validator("rewrites", mode="before")
    @classmethod
    def keep_first_five(cls, v):
        # More than five is harmless; fewer than three is a format error.
        return v[:5] if isinstance(v, list) else v


# ---------- Responses ----------


class Bands(BaseModel):
    task_response: int
    coherence_cohesion: int
    lexical_resource: int
    grammatical_range_accuracy: int
    overall: Decimal


class EssaySummary(BaseModel):
    id: int
    question: str
    word_count: int
    overall_band: Decimal
    created_at: datetime


class EssayDetail(BaseModel):
    id: int
    question: str
    essay: str
    word_count: int
    bands: Bands
    feedback: dict
    rewrites: list
    model: str
    created_at: datetime


class ProgressPoint(BaseModel):
    id: int
    created_at: datetime
    overall: Decimal
    task_response: int
    coherence_cohesion: int
    lexical_resource: int
    grammatical_range_accuracy: int


class QuotaOut(BaseModel):
    used: int
    limit: int
    remaining: int
    resets_at: datetime
