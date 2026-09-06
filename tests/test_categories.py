"""Categories: listed (alphabetically) by any user, created by admins only,
names validated and unique, and usable on tickets once created.

Categories are a small admin-managed reference table, seeded with real
helpdesk queues; there is deliberately no update or delete endpoint.
"""


# --- Listing ----------------------------------------------------------------


def test_list_categories_requires_auth(client):
    assert client.get("/categories").status_code == 401


def test_list_categories(authed_client, category):
    response = authed_client.get("/categories")
    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Network"]


def test_list_categories_is_alphabetical(authed_client, admin_client):
    # The list feeds dropdowns; a stable alphabetical order is part of the
    # contract, regardless of creation order.
    for name in ("Printer", "Account Access", "Hardware"):
        assert admin_client.post("/categories", json={"name": name}).status_code == 201

    names = [c["name"] for c in authed_client.get("/categories").json()]
    assert names == ["Account Access", "Hardware", "Printer"]


# --- Creating ---------------------------------------------------------------


def test_create_category_requires_auth(client):
    # No token at all: 401, distinct from the non-admin 403 below.
    assert client.post("/categories", json={"name": "Hardware"}).status_code == 401


def test_create_category_denied_for_regular_user(authed_client):
    # Authenticated but not permitted: managing the category list is an
    # admin responsibility.
    response = authed_client.post("/categories", json={"name": "Hardware"})
    assert response.status_code == 403


def test_create_category_as_admin(admin_client):
    response = admin_client.post("/categories", json={"name": "Hardware"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Hardware"
    assert isinstance(body["id"], int)


def test_created_category_is_usable_on_tickets(authed_client, admin_client):
    # The point of the table: a new category can be attached to a ticket and
    # comes back embedded (id + name) in the ticket's representation.
    created = admin_client.post("/categories", json={"name": "Hardware"}).json()
    ticket = authed_client.post("/tickets", json={"title": "Dead monitor", "category_id": created["id"]})
    assert ticket.status_code == 201
    assert ticket.json()["category"] == {"id": created["id"], "name": "Hardware"}


# --- Validation -------------------------------------------------------------


def test_blank_category_name_rejected(admin_client):
    # Names are trimmed and must contain text (schemas.NonBlank).
    assert admin_client.post("/categories", json={"name": "   "}).status_code == 422
    response = admin_client.post("/categories", json={"name": "  Hardware  "})
    assert response.status_code == 201
    assert response.json()["name"] == "Hardware"


def test_overlong_category_name_rejected(admin_client):
    assert admin_client.post("/categories", json={"name": "x" * 101}).status_code == 422


def test_create_duplicate_category_rejected(admin_client, category):
    # 409 Conflict: the name is valid, it just already exists. The unique
    # constraint backs this even under concurrent creates.
    response = admin_client.post("/categories", json={"name": category.name})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
