"""Auth + registration tests."""


def test_register_school_succeeds_and_returns_token(client):
    r = client.post("/api/v1/auth/register-school", json={
        "school_name": "Lincoln Test", "admin_name": "Alice",
        "admin_email": "alice@lincoln.edu", "admin_password": "longenoughpassword",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"]
    assert body["role"] == "ADMIN"
    assert body["school_id"]


def test_duplicate_school_name_rejected(client):
    payload = {"school_name": "Dup", "admin_name": "A",
               "admin_email": "a@a.com", "admin_password": "longenoughpassword"}
    r1 = client.post("/api/v1/auth/register-school", json=payload)
    assert r1.status_code == 201
    payload["admin_email"] = "b@b.com"
    r2 = client.post("/api/v1/auth/register-school", json=payload)
    assert r2.status_code == 409


def test_login_with_wrong_password_returns_401(client, school_a):
    r = client.post("/api/v1/auth/login", json={
        "email": "admin@alpha.edu", "password": "WRONG-PASSWORD",
    })
    assert r.status_code == 401


def test_login_success_and_me(client, school_a):
    r = client.post("/api/v1/auth/login", json={
        "email": "admin@alpha.edu", "password": "longenoughpassword",
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@alpha.edu"


def test_missing_token_returns_401(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_invalid_token_returns_401(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401
