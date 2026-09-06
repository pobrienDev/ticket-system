"""Shared pytest configuration and fixtures for the backend suite.

Everything in this file exists to make each test start from a known, isolated
state while exercising the *real* application code:

* the real FastAPI app, routing, dependency injection, and validation;
* the real auth path — fixtures log in over HTTP and carry genuine tokens;
* a real database (in-memory SQLite locally, Postgres in CI), recreated from
  scratch for every test.

The only things swapped out are the database *engine* (via FastAPI's
dependency-override seam) and the environment, which is pinned before the
app is imported so no developer's .env can leak into a test run.
"""

import os

# --- Environment ------------------------------------------------------------
# These must be set BEFORE any `app` module is imported: auth.py reads
# JWT_SECRET at import time and rate_limit.py reads RATE_LIMIT_ENABLED at
# import time. (That ordering is why this file has an E402 lint exemption.)
#
# JWT_SECRET uses setdefault so an explicitly exported secret still wins; the
# placeholder is padded past PyJWT's 32-byte minimum so it never warns.
# RATE_LIMIT_ENABLED is forced off so fixtures can log in repeatedly without
# tripping the login limiter.
# SENDGRID_API_KEY is set to an EMPTY string rather than deleted: app modules
# call load_dotenv(), which only fills in *missing* keys from .env. A key that
# is present-but-empty cannot be overridden, so the suite can never send real
# email even if the developer's .env contains a live key.
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-padded-to-32B")
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["SENDGRID_API_KEY"] = ""

# "sqlite://" with no path is an in-memory database. CI sets TEST_DATABASE_URL
# to a Postgres URL so the same tests also run on the production engine.
# DATABASE_URL is pointed at it too so app.database builds a matching engine
# (that engine is otherwise unused: get_db is overridden below).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth import hash_password
from app.database import Base
from app.dependencies import get_db
from app.main import app

# --- Test engine ------------------------------------------------------------
# An in-memory SQLite database exists *per connection*: open a second
# connection and you get a second, empty database. StaticPool makes the pool
# hand out one shared connection, so every session in a test (the app's
# request sessions and the `db` fixture) sees the same schema and rows.
# check_same_thread=False is required because TestClient runs the app on a
# different thread from the test function.
if TEST_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # Mirror app/database.py: SQLite ignores foreign keys unless this pragma
    # runs on each connection. Without it, tests would pass on SQLite while
    # Postgres (CI) enforced constraints the tests never exercised.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    engine = create_engine(TEST_DATABASE_URL)

TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    # Same shape as app.dependencies.get_db, bound to the test engine. Because
    # it is a yield-dependency, FastAPI closes the session after each request
    # exactly as in production.
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# FastAPI's built-in seam for swapping a dependency: every handler that
# declares `Depends(get_db)` now receives a test-engine session, and no
# application code changes.
app.dependency_overrides[get_db] = override_get_db

# One password for every fixture user, so tests can log in without carrying
# credentials around. bcrypt hashing is deliberately slow, which is most of
# the suite's runtime.
TEST_PASSWORD = "testpass123"


# --- Isolation --------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_database():
    """Drop and recreate the whole schema before every test.

    autouse=True means every test gets this without asking for it, so no test
    can observe rows left by another. dispose() first closes any pooled
    connections from the previous test; on Postgres in CI, DDL against a
    table with a lingering open connection can block or race, and this
    prevents it. (On in-memory SQLite, dropping the only connection also
    discards the database, which is fine — create_all rebuilds it.)
    """
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    """A session for tests that need to set up or inspect rows directly
    (for example, asserting on audit_log_entries after a PATCH)."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """An unauthenticated HTTP client. Using TestClient as a context manager
    runs the app's startup/shutdown lifecycle around the test."""
    with TestClient(app) as test_client:
        yield test_client


# --- Users and authentication ----------------------------------------------


def make_user(db, email, is_admin=False):
    """Insert a user directly (not through /auth/register) so user setup does
    not depend on the registration endpoint working."""
    user = models.User(email=email, hashed_password=hash_password(TEST_PASSWORD), is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user(db):
    """The default regular user; most tests act as this account."""
    return make_user(db, "user@example.com")


@pytest.fixture
def other_user(db):
    """A second regular user, for ownership and visibility tests."""
    return make_user(db, "other@example.com")


@pytest.fixture
def admin_user(db):
    return make_user(db, "admin@example.com", is_admin=True)


def login(client, email):
    """Obtain a real JWT through the login endpoint.

    The endpoint implements the OAuth2 password grant, so credentials go as
    form fields (data=), not JSON. Asserting here means a broken login fails
    loudly in the fixture rather than as a confusing 401 inside a test.
    """
    response = client.post("/auth/login", data={"username": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def authed_client(client, test_user):
    """The shared client, signed in as test_user. Setting the header on the
    client makes every subsequent request in the test authenticated."""
    token = login(client, test_user.email)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def admin_client(admin_user):
    """A SEPARATE TestClient signed in as the admin.

    It must be a distinct instance rather than the shared `client`, so a test
    can hold a regular-user client and an admin client at the same time
    (e.g. the user creates a ticket, the admin assigns it, the user reads
    the result).
    """
    with TestClient(app) as admin_test_client:
        token = login(admin_test_client, admin_user.email)
        admin_test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield admin_test_client


# --- Reference data ---------------------------------------------------------


@pytest.fixture
def category(db):
    """One category row for tests that need a valid category_id."""
    cat = models.Category(name="Network")
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
