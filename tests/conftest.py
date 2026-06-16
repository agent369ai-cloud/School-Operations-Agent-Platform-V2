"""Test fixtures.

Each test gets a fresh in-memory SQLite DB and a TestClient.
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Force fresh in-memory DB for the test session
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-which-is-long-enough"
os.environ["OPENAI_API_KEY"] = ""  # ensure parser fallback path runs

# Path so `from app...` works whether pytest is run from root or tests/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import models  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(db_engine):
    TestSession = sessionmaker(bind=db_engine)
    s = TestSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db_engine):
    TestSession = sessionmaker(bind=db_engine)

    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, school_name, email):
    r = client.post("/api/v1/auth/register-school", json={
        "school_name": school_name, "admin_name": "Admin " + school_name,
        "admin_email": email, "admin_password": "longenoughpassword",
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def school_a(client):
    return _register(client, "Alpha High", "admin@alpha.edu")


@pytest.fixture
def school_b(client):
    return _register(client, "Beta High", "admin@beta.edu")
