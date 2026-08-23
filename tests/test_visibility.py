"""Non-admins may only see tickets they own or are assigned to."""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login, make_user


def create_ticket(client, title="Someone's ticket"):
    response = client.post("/tickets", json={"title": title})
    assert response.status_code == 201
    return response.json()


def client_for(db, email, is_admin=False):
    make_user(db, email, is_admin=is_admin)
    c = TestClient(app)
    token = login(c, email)
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


def test_other_users_tickets_are_invisible(authed_client, db):
    made = create_ticket(authed_client)
    stranger = client_for(db, "stranger@example.com")

    assert stranger.get("/tickets").json()["total"] == 0
    assert stranger.get(f"/tickets/{made['id']}").status_code == 404
    assert stranger.get(f"/tickets/{made['id']}/audit").status_code == 404
    assert (
        stranger.post(f"/tickets/{made['id']}/comments", json={"body": "hi"}).status_code == 404
    )


def test_admin_sees_all_tickets(authed_client, admin_client):
    made = create_ticket(authed_client)
    assert admin_client.get(f"/tickets/{made['id']}").status_code == 200
    assert admin_client.get("/tickets").json()["total"] == 1


def test_assignee_can_see_and_work_ticket(authed_client, admin_client, db):
    made = create_ticket(authed_client)
    agent_client = client_for(db, "agent@example.com")
    agent_id = agent_client.get("/users/me").json()["id"]
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": agent_id})

    assert agent_client.get(f"/tickets/{made['id']}").status_code == 200
    # The assignee works the ticket: status changes allowed...
    response = agent_client.patch(f"/tickets/{made['id']}", json={"status": "in_progress"})
    assert response.status_code == 200
    # ...but assignment itself stays admin-only.
    assert (
        agent_client.patch(f"/tickets/{made['id']}", json={"assignee_id": None}).status_code == 403
    )


def test_owner_filter(authed_client, admin_client, test_user):
    create_ticket(authed_client, title="Mine")
    create_ticket(admin_client, title="Admin's")

    response = admin_client.get("/tickets", params={"owner_id": test_user.id})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Mine"
