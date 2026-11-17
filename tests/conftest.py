import json
import os

# Settings are read from the environment: set safe test values before importing the app.
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123")
os.environ["LLM_PROVIDER"] = "fake"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app import db  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.deps import get_llm_provider  # noqa: E402
from app.llm import FakeProvider  # noqa: E402
from app.llm.fake import build_demo_answer  # noqa: E402
from app.main import app  # noqa: E402

QUESTION = (
    "Some people believe that university education should be free for everyone. "
    "To what extent do you agree or disagree?"
)

ESSAY = """In many countries, the cost of higher education has risen sharply in recent decades. \
Some people argue that universities should not charge any fees at all. I partly agree with \
this view, because free education brings clear social benefits, but I also believe that some \
contribution from students is reasonable.

On the one hand, free university education gives every talented young person the same \
opportunity to study. Students from poor families often cannot afford high tuition fees, so \
they choose to work immediately after school. As a result, society loses many skilled doctors, \
engineers and teachers. In addition, graduates usually earn higher salaries and pay more tax, \
which means that the government eventually recovers much of the money it invests.

On the other hand, universities need large budgets to pay lecturers, build laboratories and \
support research. If the state pays for everything, taxpayers who never attended university \
have to cover the cost for others. Moreover, when education is completely free, some students \
may not take their studies seriously and may change courses many times without a clear plan.

In my opinion, the best solution is a mixed system. Tuition should be free or very cheap for \
students from low income families, while others could pay moderate fees or repay a loan after \
they start working. This approach keeps university open to everyone and still shares the cost \
fairly between students and society.

In conclusion, although free university education has important advantages, I believe a \
balanced model with targeted support is more sustainable for most countries."""


def valid_answer(essay: str = ESSAY, language: str = "en") -> str:
    return build_demo_answer(essay, language)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            events.append((name, data))
    return events


@pytest.fixture
def settings() -> Settings:
    return Settings(user_daily_limit=5, global_daily_limit=100)


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider([])


@pytest.fixture
async def client(tmp_path, settings, fake_provider):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = db.init_engine(url, null_pool=True)
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.drop_all)
        await conn.run_sync(db.Base.metadata.create_all)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_provider] = lambda: fake_provider
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.drop_all)
    await engine.dispose()


async def register_and_login(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def alice(client) -> dict:
    return await register_and_login(client, "alice@example.com")


@pytest.fixture
async def bob(client) -> dict:
    return await register_and_login(client, "bob@example.com")


async def grade(client, headers, *, essay: str = ESSAY, question: str = QUESTION):
    r = await client.post(
        "/api/essays",
        json={"question": question, "essay": essay, "feedback_language": "en"},
        headers=headers,
    )
    events = parse_sse(r.text) if r.status_code == 200 else []
    return r, events
