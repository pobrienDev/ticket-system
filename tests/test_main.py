"""App-level wiring in app/main.py: health check, security headers, docs."""

from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.dependencies import get_db
from app.main import app, docs_settings


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_503_when_the_database_fails(client):
    # Swap the session for one whose execute() fails the way a dead database
    # does. Restored afterwards so other tests keep the test engine.
    broken = MagicMock()
    broken.execute.side_effect = OperationalError("SELECT 1", {}, Exception("connection refused"))
    original = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = lambda: broken
    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides[get_db] = original

    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"


def test_security_headers_on_every_response(client):
    # Present on a success and on an error alike: the middleware wraps the
    # whole app, not individual routes.
    for path, expected in (("/health", 200), ("/tickets", 401)):
        response = client.get(path)
        assert response.status_code == expected
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "same-origin"


def test_docs_available_in_development(client):
    # The suite runs with the default APP_ENV (development).
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_disabled_in_production():
    # Decided at app construction, so the rule is tested as a function.
    assert docs_settings("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert docs_settings("development") == {}
    assert docs_settings("staging") == {}
