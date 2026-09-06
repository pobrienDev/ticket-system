"""Category listing (any user) and creation (admin only, duplicates rejected)."""


def test_list_categories_requires_auth(client):
    assert client.get("/categories").status_code == 401


def test_list_categories(authed_client, category):
    response = authed_client.get("/categories")
    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Network"]


def test_create_category_denied_for_regular_user(authed_client):
    response = authed_client.post("/categories", json={"name": "Hardware"})
    assert response.status_code == 403


def test_create_category_as_admin(admin_client):
    response = admin_client.post("/categories", json={"name": "Hardware"})
    assert response.status_code == 201
    assert response.json()["name"] == "Hardware"


def test_blank_category_name_rejected(admin_client):
    assert admin_client.post("/categories", json={"name": "   "}).status_code == 422
    response = admin_client.post("/categories", json={"name": "  Hardware  "})
    assert response.status_code == 201
    assert response.json()["name"] == "Hardware"


def test_create_duplicate_category_rejected(admin_client, category):
    response = admin_client.post("/categories", json={"name": category.name})
    assert response.status_code == 409
