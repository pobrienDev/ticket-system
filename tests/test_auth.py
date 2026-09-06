"""Registration, login, token validation, and admin gating on user lookups.

These tests exercise the real credential path end to end: bcrypt hashing on
register, the OAuth2 password-grant form on login, JWT issue and verify, and
the per-request user reload in get_current_user. Nothing in the auth stack
is mocked.
"""

from app.auth import create_access_token
from tests.conftest import TEST_PASSWORD

# --- Registration -----------------------------------------------------------


def test_register_success(client):
    response = client.post(
        "/auth/register", json={"email": "new@example.com", "password": "longenough123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    # Self-registration must never grant admin.
    assert body["is_admin"] is False
    # The response schema decides what leaves the server; no form of the
    # password may appear in it.
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email_rejected(client, test_user):
    response = client.post(
        "/auth/register", json={"email": test_user.email, "password": "longenough123"}
    )
    # 409 Conflict, not 400: the request is well-formed, it conflicts with state.
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


def test_register_invalid_email_rejected(client):
    # EmailStr validation runs before the handler; nothing is created.
    response = client.post("/auth/register", json={"email": "not-an-email", "password": "longenough123"})
    assert response.status_code == 422


def test_register_short_password_rejected(client):
    response = client.post("/auth/register", json={"email": "new@example.com", "password": "short"})
    assert response.status_code == 422


def test_register_overlong_password_rejected(client):
    # bcrypt truncates at 72 bytes; longer passwords must be rejected, not silently clipped.
    response = client.post("/auth/register", json={"email": "new@example.com", "password": "x" * 73})
    assert response.status_code == 422


def test_email_is_case_insensitive(client):
    response = client.post(
        "/auth/register", json={"email": "Mixed.Case@Example.com", "password": "longenough123"}
    )
    assert response.status_code == 201
    # Stored lowercased, so there is exactly one canonical form per account.
    assert response.json()["email"] == "mixed.case@example.com"

    # Same email in different case is the same account...
    response = client.post(
        "/auth/register", json={"email": "MIXED.CASE@example.com", "password": "longenough123"}
    )
    assert response.status_code == 409

    # ...and login works regardless of the case typed.
    response = client.post(
        "/auth/login", data={"username": "mixed.CASE@EXAMPLE.com", "password": "longenough123"}
    )
    assert response.status_code == 200


# --- Login ------------------------------------------------------------------
# Login is the OAuth2 password grant: credentials are sent as form fields
# (data=), not JSON, which is why these requests differ from the rest.


def test_login_success(client, test_user):
    response = client.post(
        "/auth/login", data={"username": test_user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(client, test_user):
    response = client.post(
        "/auth/login", data={"username": test_user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_unknown_user_rejected(client):
    response = client.post(
        "/auth/login", data={"username": "ghost@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


def test_login_failures_are_indistinguishable(client, test_user):
    # Enumeration defense: an attacker must not be able to tell "no such
    # account" from "wrong password". Status AND message must match.
    wrong_password = client.post(
        "/auth/login", data={"username": test_user.email, "password": "wrong-password"}
    )
    unknown_user = client.post(
        "/auth/login", data={"username": "ghost@example.com", "password": TEST_PASSWORD}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["detail"] == unknown_user.json()["detail"]


# --- Token validation -------------------------------------------------------


def test_me_requires_auth(client):
    response = client.get("/users/me")
    assert response.status_code == 401
    # The 401 tells the client which auth scheme to use.
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_me_returns_current_user(authed_client, test_user):
    response = authed_client.get("/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email


def test_garbage_token_rejected(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_expired_token_rejected(client, test_user):
    # A correctly signed token whose exp is in the past must still be
    # rejected; PyJWT validates the exp claim as part of decode.
    expired = create_access_token({"sub": str(test_user.id)}, expires_minutes=-1)
    response = client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_token_for_deleted_user_rejected(authed_client, test_user, db):
    # The JWT is stateless, but get_current_user re-reads the user row on
    # every request, so removing the account revokes access immediately
    # even though the token itself is still validly signed and unexpired.
    assert authed_client.get("/users/me").status_code == 200
    db.delete(db.get(type(test_user), test_user.id))
    db.commit()
    assert authed_client.get("/users/me").status_code == 401


# --- Admin gating -----------------------------------------------------------


def test_list_users_denied_for_regular_user(authed_client):
    # 403, not 401: the caller is authenticated, just not permitted.
    assert authed_client.get("/users").status_code == 403


def test_list_users_allowed_for_admin(admin_client, test_user):
    response = admin_client.get("/users")
    assert response.status_code == 200
    emails = [u["email"] for u in response.json()]
    assert test_user.email in emails
