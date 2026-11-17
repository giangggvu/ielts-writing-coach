import asyncio
from datetime import UTC, datetime

import pytest

from app import db
from app.config import Settings
from app.quota import current_day
from tests.conftest import grade, register_and_login, valid_answer


async def test_sixth_essay_of_the_day_is_refused(client, alice, fake_provider):
    fake_provider._answers = [valid_answer() for _ in range(5)]
    for _ in range(5):
        r, events = await grade(client, alice)
        assert events[-1][0] == "result"

    r, _ = await grade(client, alice)

    assert r.status_code == 429
    assert "5 essays per day" in r.json()["detail"]
    assert len(fake_provider.calls) == 5  # refused before calling the AI
    quota = (await client.get("/api/quota", headers=alice)).json()
    assert (quota["used"], quota["limit"], quota["remaining"]) == (5, 5, 0)


async def test_failed_attempts_do_not_use_the_users_quota(client, alice, fake_provider):
    fake_provider._answers = ["bad", "bad"] * 5 + [valid_answer() for _ in range(5)]
    for _ in range(5):
        _, events = await grade(client, alice)
        assert events[-1][0] == "error"
    for _ in range(5):
        _, events = await grade(client, alice)
        assert events[-1][0] == "result"


async def test_limit_is_per_user(client, alice, bob, fake_provider):
    fake_provider._answers = [valid_answer() for _ in range(6)]
    for _ in range(5):
        await grade(client, alice)
    r, events = await grade(client, bob)
    assert r.status_code == 200
    assert events[-1][0] == "result"


async def test_global_daily_cap_protects_the_budget(client, settings, fake_provider):
    settings.global_daily_limit = 3
    users = [await register_and_login(client, f"u{i}@example.com") for i in range(3)]
    # Failed attempts still cost money, so they count towards the global cap.
    fake_provider._answers = [valid_answer(), "bad", "bad", valid_answer()]
    _, e1 = await grade(client, users[0])
    _, e2 = await grade(client, users[1])
    _, e3 = await grade(client, users[2])
    assert [e1[-1][0], e2[-1][0], e3[-1][0]] == ["result", "error", "result"]

    newcomer = await register_and_login(client, "late@example.com")
    r, _ = await grade(client, newcomer)
    assert r.status_code == 429
    assert "budget" in r.json()["detail"]


async def test_parallel_requests_cannot_overshoot_the_limit(client, alice, settings, fake_provider):
    if db.get_sessionmaker().kw["bind"].dialect.name != "postgresql":
        pytest.skip("Row locking is a PostgreSQL feature; run with TEST_DATABASE_URL")
    settings.user_daily_limit = 2
    fake_provider._answers = [valid_answer() for _ in range(8)]

    responses = await asyncio.gather(*(grade(client, alice) for _ in range(8)))

    codes = sorted(r.status_code for r, _ in responses)
    assert codes == [200, 200] + [429] * 6


def test_day_boundary_follows_configured_timezone():
    s = Settings(quota_timezone="Asia/Ho_Chi_Minh")
    # 18:30 UTC on 1 Mar is already 01:30 on 2 Mar in Vietnam (UTC+7)
    day = current_day(s, datetime(2026, 3, 1, 18, 30, tzinfo=UTC))
    assert day.start.astimezone(UTC) == datetime(2026, 3, 1, 17, 0, tzinfo=UTC)
    assert (day.end - day.start).days == 1
