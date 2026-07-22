from tests.conftest import TEST_PASSWORD


def test_register_success(client):
    response = client.post(
        "/auth/register", json={"email": "new@example.com", "password": "longenough123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["is_admin"] is False
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email_rejected(client, test_user):
    response = client.post(
        "/auth/register", json={"email": test_user.email, "password": "longenough123"}
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_register_short_password_rejected(client):
    response = client.post("/auth/register", json={"email": "new@example.com", "password": "short"})
    assert response.status_code == 422


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


def test_me_requires_auth(client):
    assert client.get("/users/me").status_code == 401


def test_me_returns_current_user(authed_client, test_user):
    response = authed_client.get("/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email


def test_garbage_token_rejected(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_list_users_denied_for_regular_user(authed_client):
    assert authed_client.get("/users").status_code == 403


def test_list_users_allowed_for_admin(admin_client, test_user):
    response = admin_client.get("/users")
    assert response.status_code == 200
    emails = [u["email"] for u in response.json()]
    assert test_user.email in emails
