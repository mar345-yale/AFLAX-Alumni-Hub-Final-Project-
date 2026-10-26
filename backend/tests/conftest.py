"""Test setup: every test session runs against a fresh, seeded database in a temp folder,
so the real data/aflax.db is never touched. No model calls are made (the agent is only
imported; its output validator and tools are tested directly).

Run from backend/:  python -m pytest
"""

import os
import sys
import tempfile
from pathlib import Path

# Must happen before any backend module is imported (db.py reads it at import time).
os.environ["AFLAX_DATA_DIR"] = tempfile.mkdtemp(prefix="aflax-test-")
os.environ.pop("SMTP_HOST", None)  # keep email in the outbox
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import ratelimit  # noqa: E402
import seed  # noqa: E402

seed.seed(reset=True)

import main  # noqa: E402

ADMIN_EMAIL = seed.ADMIN["email"]
ADMIN_PASSWORD = seed.ADMIN["password"]


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    ratelimit.reset_all()
    yield
    ratelimit.reset_all()


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def login(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def admin(client: TestClient) -> dict:
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


_counter = iter(range(1, 10_000))


def signup_form(**overrides) -> dict:
    n = next(_counter)
    email = overrides.pop("email", f"member{n}@example.com")
    form = {
        "email": email, "confirm_email": email,
        "password": "goFalcons1", "confirm_password": "goFalcons1",
        "first_name": "Test", "last_name": f"Member{n}", "grad_year": "2015",
        "status": "Civilian", "city": "Denver, CO", "job": "Engineer",
        "phone": "(719) 555-0100", "willing_to_mentor": "true",
    }
    form.update(overrides)
    return form


@pytest.fixture
def approved_member(client: TestClient, admin: dict):
    """Sign up a member, approve them, and return (headers, email, user_id)."""
    form = signup_form()
    assert client.post("/api/auth/signup", data=form).status_code == 201
    accounts = client.get("/api/admin/accounts", headers=admin).json()["accounts"]
    user_id = next(a["id"] for a in accounts if a["email"] == form["email"])
    client.post(f"/api/admin/accounts/{user_id}/approve", headers=admin)
    return login(client, form["email"], form["password"]), form["email"], user_id
