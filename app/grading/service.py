import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.db import get_sessionmaker
from app.grading.parser import FormatError, GradingResult, SectionStreamParser, build_result
from app.grading.prompt import RETRY_SUFFIX, SYSTEM_PROMPT, build_user_prompt
from app.llm import LLMProvider, ProviderError
from app.models import Essay, EssayStatus, utcnow

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # first try + one retry when the format is wrong

FORMAT_FAILED_MESSAGE = (
    "The AI answered in an unexpected format twice, so no score was saved. "
    "This attempt does not count towards your daily limit."
)
UNEXPECTED_MESSAGE = (
    "Something went wrong while grading. This attempt does not count towards your daily limit."
)


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _mark_failed(essay_id: int, reason: str) -> None:
    async with get_sessionmaker()() as session:
        essay = await session.get(Essay, essay_id)
        if essay and essay.status == EssayStatus.PENDING:
            essay.status = EssayStatus.FAILED
            essay.error_message = reason[:2000]
            await session.commit()


async def _save(essay_id: int, result: GradingResult) -> None:
    async with get_sessionmaker()() as session:
        essay = await session.get(Essay, essay_id)
        if essay is None:
            raise RuntimeError(f"Essay {essay_id} disappeared")
        essay.task_response = result.bands["task_response"]
        essay.coherence_cohesion = result.bands["coherence_cohesion"]
        essay.lexical_resource = result.bands["lexical_resource"]
        essay.grammatical_range_accuracy = result.bands["grammatical_range_accuracy"]
        essay.overall_band = result.overall
        essay.feedback = result.feedback
        essay.rewrites = result.rewrites
        essay.status = EssayStatus.COMPLETED
        essay.completed_at = utcnow()
        await session.commit()


async def grade_stream(
    essay_id: int,
    question: str,
    essay_text: str,
    language: str,
    provider: LLMProvider,
) -> AsyncIterator[str]:
    """Run the model, stream feedback as SSE, validate, then save. Never raises."""
    finished = False
    try:
        base_prompt = build_user_prompt(question, essay_text, language)
        last_error: FormatError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                yield sse("retry", {"attempt": attempt, "reason": "format"})
            prompt = base_prompt if attempt == 1 else base_prompt + RETRY_SUFFIX
            parser = SectionStreamParser()
            try:
                async for chunk in provider.stream(SYSTEM_PROMPT, prompt):
                    for criterion, text in parser.feed(chunk):
                        yield sse("feedback", {"criterion": criterion, "text": text})
                for criterion, text in parser.finish():
                    yield sse("feedback", {"criterion": criterion, "text": text})
                result = build_result(parser, essay_text)
            except FormatError as exc:
                log.warning("Essay %s attempt %s: bad format: %s", essay_id, attempt, exc)
                last_error = exc
                continue
            except ProviderError as exc:
                await _mark_failed(essay_id, f"provider: {exc}")
                finished = True
                yield sse("error", {"message": str(exc), "counted": False})
                return

            if result.dropped_quotes:
                log.info("Essay %s: dropped %s invented quotes", essay_id, result.dropped_quotes)
            await _save(essay_id, result)
            finished = True
            yield sse(
                "result",
                {
                    "id": essay_id,
                    "bands": {**result.bands, "overall": float(result.overall)},
                    "feedback": result.feedback,
                    "rewrites": result.rewrites,
                },
            )
            return

        await _mark_failed(essay_id, f"format: {last_error}")
        finished = True
        yield sse("error", {"message": FORMAT_FAILED_MESSAGE, "counted": False})
    except Exception:
        log.exception("Unexpected error while grading essay %s", essay_id)
        await _mark_failed(essay_id, "unexpected error")
        finished = True
        yield sse("error", {"message": UNEXPECTED_MESSAGE, "counted": False})
    finally:
        if not finished:  # client disconnected mid-stream
            try:
                await asyncio.shield(_mark_failed(essay_id, "client disconnected"))
            except Exception:  # noqa: BLE001
                log.exception("Could not mark essay %s as failed", essay_id)
