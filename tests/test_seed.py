"""The seed script in app/seed.py, run for real against the test database.

It stands behind the Docker quick start, the demo logins, and the admin
bootstrap, so a broken seed is a broken first impression — and it had no
tests. These run the actual seed() with its session factory pointed at the
test engine, then log in through the API like a person would.
"""

import pytest

from app import models
from app import seed as seed_module
from tests.conftest import TEST_PASSWORD, TestSessionLocal


@pytest.fixture(autouse=True)
def seed_against_test_engine(monkeypatch):
    # seed() opens its own sessions from app.database.SessionLocal, which is
    # bound to the app engine, not the test engine. Point it at the test one
    # so the rows land where the client fixture can see them.
    monkeypatch.setattr(seed_module, "SessionLocal", TestSessionLocal)
    # A developer's .env may carry admin or demo credentials; each test sets
    # exactly what it wants to exercise.
    for name in ("ADMIN_EMAIL", "ADMIN_PASSWORD", "DEMO_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def test_demo_users_log_in_with_the_default_password_when_the_env_is_blank(client, monkeypatch):
    # `copy .env.example .env` leaves DEMO_PASSWORD= with an empty value, and
    # load_dotenv() sets it to "" rather than leaving it unset. That must still
    # mean "use the default", or every demo login in the README is wrong.
    monkeypatch.setenv("DEMO_PASSWORD", "")
    seed_module.seed(demo=True)
    for email, _is_admin in seed_module.DEMO_USERS:
        response = client.post("/auth/login", data={"username": email, "password": "demo1234"})
        assert response.status_code == 200, email


def test_seed_is_idempotent(db):
    seed_module.seed(demo=True)
    seed_module.seed(demo=True)
    assert db.query(models.Category).count() == len(seed_module.DEFAULT_CATEGORIES)
    assert db.query(models.User).count() == len(seed_module.DEMO_USERS)
    assert db.query(models.Ticket).count() == len(seed_module.DEMO_TICKETS)


def test_seed_creates_the_categories_and_an_admin(db, client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Boss@Example.com")  # stored lowercased, like registration
    monkeypatch.setenv("ADMIN_PASSWORD", TEST_PASSWORD)
    seed_module.seed()
    assert sorted(c.name for c in db.query(models.Category)) == sorted(seed_module.DEFAULT_CATEGORIES)
    admin = db.query(models.User).filter(models.User.email == "boss@example.com").one()
    assert admin.is_admin
    login = client.post("/auth/login", data={"username": "boss@example.com", "password": TEST_PASSWORD})
    assert login.status_code == 200
