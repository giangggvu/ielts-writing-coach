async def test_register_login_and_me(client):
    r = await client.post(
        "/api/auth/register", json={"email": "New@Example.com", "password": "password123"}
    )
    assert r.status_code == 201
    assert r.json()["email"] == "new@example.com"
    assert "password" not in r.text

    r = await client.post(
        "/api/auth/login", json={"email": "new@example.com", "password": "password123"}
    )
    token = r.json()["access_token"]
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "new@example.com"


async def test_duplicate_email_is_rejected(client, alice):
    r = await client.post(
        "/api/auth/register", json={"email": "ALICE@example.com", "password": "password123"}
    )
    assert r.status_code == 409


async def test_wrong_password_and_unknown_email_look_the_same(client, alice):
    wrong = await client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "nope-nope"}
    )
    unknown = await client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_short_password_is_rejected(client):
    r = await client.post("/api/auth/register", json={"email": "a@b.co", "password": "short"})
    assert r.status_code == 422


async def test_protected_routes_need_a_valid_token(client):
    assert (await client.get("/api/essays")).status_code == 401
    r = await client.get("/api/essays", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401
