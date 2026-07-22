import os

# Must be set before any app module is imported. SENDGRID_API_KEY is set to a
# falsy value rather than popped: app imports call load_dotenv(), which fills
# in missing keys from .env — a present-but-empty value can't be overridden,
# so tests can never make real email calls even if .env has a key.
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["SENDGRID_API_KEY"] = ""
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth import hash_password
from app.database import Base
from app.dependencies import get_db
from app.main import app

# A dedicated test engine. For SQLite this is in-memory on a single shared
# connection (StaticPool), so per-test drop/create can never race in-flight
# connections from a previous test. CI sets TEST_DATABASE_URL to Postgres.
if TEST_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
else:
    engine = create_engine(TEST_DATABASE_URL)

TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

TEST_PASSWORD = "testpass123"


@pytest.fixture(autouse=True)
def fresh_database():
    # Close any pooled connections from the previous test before DDL so the
    # drop/create can't race lingering sessions (matters for Postgres in CI).
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_user(db, email, is_admin=False):
    user = models.User(email=email, hashed_password=hash_password(TEST_PASSWORD), is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user(db):
    return make_user(db, "user@example.com")


@pytest.fixture
def other_user(db):
    return make_user(db, "other@example.com")


@pytest.fixture
def admin_user(db):
    return make_user(db, "admin@example.com", is_admin=True)


def login(client, email):
    response = client.post("/auth/login", data={"username": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def authed_client(client, test_user):
    token = login(client, test_user.email)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def admin_client(admin_user):
    # A separate TestClient instance so admin and regular clients can coexist in one test.
    with TestClient(app) as admin_test_client:
        token = login(admin_test_client, admin_user.email)
        admin_test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield admin_test_client


@pytest.fixture
def category(db):
    cat = models.Category(name="Network")
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
