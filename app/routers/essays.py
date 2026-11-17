from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_current_user, get_llm_provider
from app.grading.service import grade_stream, sse
from app.llm import LLMProvider
from app.models import Essay, EssayStatus, User
from app.quota import QuotaExceeded, current_day, reserve_attempt, user_used
from app.schemas import (
    Bands,
    EssayDetail,
    EssaySummary,
    GradeIn,
    ProgressPoint,
    QuotaOut,
    count_words,
)

router = APIRouter(prefix="/api", tags=["essays"])


@router.get("/quota", response_model=QuotaOut)
async def quota(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> QuotaOut:
    day = current_day(settings)
    used = await user_used(session, user.id, day)
    limit = settings.user_daily_limit
    return QuotaOut(used=used, limit=limit, remaining=max(0, limit - used), resets_at=day.end)


@router.post(
    "/essays",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}, 429: {"description": "Limit hit"}},
)
async def grade_essay(
    body: GradeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    """Grade an essay. The response is a Server-Sent Events stream:

    `start` -> many `feedback` -> (`retry`) -> `result` | `error`
    """
    try:
        essay = await reserve_attempt(
            session,
            settings,
            user,
            question=body.question,
            essay_text=body.essay,
            word_count=count_words(body.essay),
            language=body.feedback_language,
            provider=provider.name,
            model=provider.model,
        )
    except QuotaExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, exc.message) from exc

    async def events():
        yield sse("start", {"id": essay.id, "word_count": essay.word_count})
        async for frame in grade_stream(
            essay.id, body.question, body.essay, body.feedback_language, provider
        ):
            yield frame

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _owned_completed(user: User):
    return select(Essay).where(Essay.user_id == user.id, Essay.status == EssayStatus.COMPLETED)


@router.get("/essays", response_model=list[EssaySummary])
async def list_essays(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EssaySummary]:
    rows = await session.scalars(
        _owned_completed(user).order_by(Essay.created_at.desc()).limit(limit).offset(offset)
    )
    return [
        EssaySummary(
            id=e.id,
            question=e.question,
            word_count=e.word_count,
            overall_band=e.overall_band,
            created_at=e.created_at,
        )
        for e in rows
    ]


@router.get("/essays/progress", response_model=list[ProgressPoint])
async def progress(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ProgressPoint]:
    """Band scores over time (oldest first) for the chart: the latest 50 essays."""
    rows = list(
        await session.scalars(_owned_completed(user).order_by(Essay.created_at.desc()).limit(50))
    )
    return [
        ProgressPoint(
            id=e.id,
            created_at=e.created_at,
            overall=e.overall_band,
            task_response=e.task_response,
            coherence_cohesion=e.coherence_cohesion,
            lexical_resource=e.lexical_resource,
            grammatical_range_accuracy=e.grammatical_range_accuracy,
        )
        for e in reversed(rows)
    ]


@router.get("/essays/{essay_id}", response_model=EssayDetail)
async def get_essay(
    essay_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EssayDetail:
    # Someone else's essay gets the same 404 as a missing one: no hint that it exists.
    essay = await session.scalar(_owned_completed(user).where(Essay.id == essay_id))
    if essay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essay not found")
    return EssayDetail(
        id=essay.id,
        question=essay.question,
        essay=essay.essay_text,
        word_count=essay.word_count,
        bands=Bands(
            task_response=essay.task_response,
            coherence_cohesion=essay.coherence_cohesion,
            lexical_resource=essay.lexical_resource,
            grammatical_range_accuracy=essay.grammatical_range_accuracy,
            overall=essay.overall_band,
        ),
        feedback=essay.feedback or {},
        rewrites=essay.rewrites or [],
        model=essay.model_name,
        created_at=essay.created_at,
    )
