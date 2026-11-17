from sqlalchemy import select

from app import db
from app.grading.prompt import RETRY_SUFFIX
from app.llm import ProviderError
from app.models import Essay, EssayStatus
from tests.conftest import ESSAY, grade, valid_answer


async def used(client, headers) -> int:
    return (await client.get("/api/quota", headers=headers)).json()["used"]


async def test_grading_streams_feedback_then_saves_validated_result(client, alice, fake_provider):
    fake_provider._answers = [valid_answer()]

    r, events = await grade(client, alice)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert names[-1] == "result"
    assert names.count("feedback") > 4  # arrives in many small pieces

    result = events[-1][1]
    assert result["bands"]["task_response"] == 6  # demo answer: >= 250 words
    assert result["bands"]["overall"] == 6.0
    assert 3 <= len(result["rewrites"]) <= 5
    quote = result["feedback"]["grammatical_range_accuracy"]["errors"][0]["quote"]
    assert quote in ESSAY

    detail = (await client.get(f"/api/essays/{result['id']}", headers=alice)).json()
    assert detail["bands"]["overall"] == "6.0"
    assert detail["essay"] == ESSAY
    assert await used(client, alice) == 1


async def test_essay_length_is_checked_before_any_ai_call(client, alice, fake_provider):
    r, _ = await grade(client, alice, essay="Too short to be a real essay. " * 5)
    assert r.status_code == 422
    assert "150-600 words" in r.text
    assert fake_provider.calls == []
    assert await used(client, alice) == 0


async def test_wrong_format_is_retried_once(client, alice, fake_provider):
    fake_provider._answers = ["I think this essay is about band 6.", valid_answer()]

    _, events = await grade(client, alice)

    names = [n for n, _ in events]
    assert "retry" in names
    assert names[-1] == "result"
    assert len(fake_provider.calls) == 2
    assert fake_provider.calls[1][1].endswith(RETRY_SUFFIX)
    assert await used(client, alice) == 1


async def test_wrong_format_twice_gives_clear_error_and_does_not_count(
    client, alice, fake_provider
):
    fake_provider._answers = ["garbage", "### TASK_RESPONSE\nok\n### JSON\n{oops"]

    _, events = await grade(client, alice)

    name, data = events[-1]
    assert name == "error"
    assert data["counted"] is False
    assert "unexpected format" in data["message"]
    assert len(fake_provider.calls) == 2  # exactly one retry, no more
    assert await used(client, alice) == 0
    assert (await client.get("/api/essays", headers=alice)).json() == []

    async with db.get_sessionmaker()() as s:
        essay = await s.scalar(select(Essay))
        assert essay.status == EssayStatus.FAILED
        assert essay.overall_band is None  # nothing unvalidated was stored


async def test_provider_error_is_reported_and_not_counted(client, alice, fake_provider):
    fake_provider._answers = [ProviderError("Gemini rate limit reached. Please try again.")]

    _, events = await grade(client, alice)

    assert events[-1] == (
        "error",
        {"message": "Gemini rate limit reached. Please try again.", "counted": False},
    )
    assert len(fake_provider.calls) == 1  # provider outages are not retried
    assert await used(client, alice) == 0
