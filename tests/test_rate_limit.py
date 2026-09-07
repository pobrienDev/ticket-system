"""Rate limiting in app/rate_limit.py.

The suite runs with RATE_LIMIT_ENABLED=false so fixtures can log in freely;
the end-to-end tests here switch the limiter on for their own duration and
reset its counters, so the advertised protection is actually exercised.
"""

import pytest
from limits import parse as parse_limit
from starlette.requests import Request

from app import rate_limit
from tests.conftest import TEST_PASSWORD


def make_request(client_ip="203.0.113.7", forwarded=None):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    scope = {"type": "http", "headers": headers, "client": (client_ip, 12345), "method": "GET", "path": "/"}
    return Request(scope)


# --- Configuration ----------------------------------------------------------


def test_limits_are_valid_limit_strings():
    # A typo here would otherwise surface as a 500 on the first login.
    for value in (rate_limit.LOGIN_RATE_LIMIT, rate_limit.REGISTER_RATE_LIMIT):
        parse_limit(value)
    register_allowed = parse_limit(rate_limit.REGISTER_RATE_LIMIT).amount
    login_allowed = parse_limit(rate_limit.LOGIN_RATE_LIMIT).amount
    assert register_allowed < login_allowed


def test_bad_limit_string_fails_at_boot(monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "ten per minute")
    with pytest.raises(RuntimeError, match="not a valid rate limit"):
        rate_limit._limit_from_env("LOGIN_RATE_LIMIT", "10/minute")


# --- Client identity --------------------------------------------------------


def test_key_is_the_peer_address_unless_proxy_headers_are_trusted(monkeypatch):
    # Default: X-Forwarded-For is ignored, so a client cannot spoof its
    # identity when there is no proxy in front to overwrite the header.
    monkeypatch.setattr(rate_limit, "TRUST_PROXY_HEADERS", False)
    request = make_request(client_ip="203.0.113.7", forwarded="198.51.100.9, 10.0.0.1")
    assert rate_limit.client_key(request) == "203.0.113.7"


def test_key_is_the_forwarded_client_when_proxy_headers_are_trusted(monkeypatch):
    # Behind a proxy every request's peer address IS the proxy; the first
    # X-Forwarded-For entry is the real client. Without this, one bucket
    # would be shared by everyone.
    monkeypatch.setattr(rate_limit, "TRUST_PROXY_HEADERS", True)
    request = make_request(client_ip="10.0.0.1", forwarded="198.51.100.9, 10.0.0.1")
    assert rate_limit.client_key(request) == "198.51.100.9"
    # ...and falls back to the peer when the header is absent.
    assert rate_limit.client_key(make_request(client_ip="10.0.0.1")) == "10.0.0.1"


# --- End to end -------------------------------------------------------------


@pytest.fixture
def limiting_enabled():
    rate_limit.limiter.reset()
    rate_limit.limiter.enabled = True
    try:
        yield
    finally:
        rate_limit.limiter.enabled = False
        rate_limit.limiter.reset()


def test_login_is_throttled_per_client(client, test_user, limiting_enabled):
    allowed = parse_limit(rate_limit.LOGIN_RATE_LIMIT).amount
    for _ in range(allowed):
        response = client.post("/auth/login", data={"username": test_user.email, "password": "wrong"})
        assert response.status_code == 401  # wrong password, but not yet throttled

    response = client.post("/auth/login", data={"username": test_user.email, "password": TEST_PASSWORD})
    # Even the correct password is refused once the bucket is exhausted:
    # the limit is on attempts, which is the point of brute-force protection.
    assert response.status_code == 429


def test_register_is_throttled_harder_than_login(client, limiting_enabled):
    allowed = parse_limit(rate_limit.REGISTER_RATE_LIMIT).amount
    for i in range(allowed):
        payload = {"email": f"u{i}@example.com", "password": "longenough123"}
        assert client.post("/auth/register", json=payload).status_code == 201

    payload = {"email": "one-too-many@example.com", "password": "longenough123"}
    assert client.post("/auth/register", json=payload).status_code == 429
