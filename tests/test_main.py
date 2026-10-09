"""App-level wiring in app/main.py: root, health check, security headers, docs."""

import os
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

import app.main as main_module
from app import auth
from app.dependencies import get_db
from app.main import app, docs_settings


def test_root_describes_the_service(client, monkeypatch):
    # Open to anyone, and needs no database: it is what a person sees when
    # they paste the service's address into a browser.
    monkeypatch.delenv("APP_URL", raising=False)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"service": app.title, "health": "/health", "docs": "/docs"}


def test_root_links_to_the_frontend_when_app_url_is_set(client, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://tickets.example.com/")
    assert client.get("/").json()["app"] == "https://tickets.example.com"


def test_root_does_not_advertise_docs_in_production(client, monkeypatch):
    # The docs routes are absent in production, so pointing at them would
    # send people to a 404.
    monkeypatch.setattr(main_module, "APP_ENV", "production")
    assert "docs" not in client.get("/").json()


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


def test_suite_pins_its_environment():
    # conftest sets these before the app is imported. A developer's .env
    # (APP_URL for email links, APP_ENV=production, another token lifetime)
    # must never change what the suite asserts; this fails loudly if a pin
    # is removed.
    assert os.environ["APP_ENV"] == "development"
    assert os.environ["APP_URL"] == ""
    assert os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] == "60"
    assert main_module.APP_ENV == "development"
    assert auth.ACCESS_TOKEN_EXPIRE_MINUTES == 60


def test_docs_available_in_development(client):
    # conftest pins APP_ENV=development for the whole suite.
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_disabled_in_production():
    # Decided at app construction, so the rule is tested as a function.
    assert docs_settings("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert docs_settings("development") == {}
    assert docs_settings("staging") == {}
