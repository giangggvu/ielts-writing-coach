from tests.conftest import ESSAY, grade, valid_answer


async def test_user_cannot_see_someone_elses_essay(client, alice, bob, fake_provider):
    fake_provider._answers = [valid_answer()]
    _, events = await grade(client, alice)
    essay_id = events[-1][1]["id"]

    assert (await client.get(f"/api/essays/{essay_id}", headers=alice)).status_code == 200

    r = await client.get(f"/api/essays/{essay_id}", headers=bob)
    assert r.status_code == 404  # same answer as a missing essay
    assert (await client.get("/api/essays", headers=bob)).json() == []
    assert (await client.get("/api/essays/progress", headers=bob)).json() == []
    assert (await client.get("/api/essays/999999", headers=bob)).status_code == 404


async def test_history_list_and_progress_chart_data(client, alice, fake_provider):
    short = " ".join(ESSAY.split()[:200])  # < 250 words -> demo gives lower Task Response
    fake_provider._answers = [valid_answer(short), valid_answer()]
    _, first = await grade(client, alice, essay=short)
    _, second = await grade(client, alice)

    listing = (await client.get("/api/essays", headers=alice)).json()
    assert [e["id"] for e in listing] == [second[-1][1]["id"], first[-1][1]["id"]]  # newest first

    points = (await client.get("/api/essays/progress", headers=alice)).json()
    assert [p["id"] for p in points] == [first[-1][1]["id"], second[-1][1]["id"]]  # oldest first
    assert points[0]["task_response"] == 5
    assert points[1]["task_response"] == 6
