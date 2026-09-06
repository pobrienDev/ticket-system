"""Non-admins may only see tickets they own or are assigned to.

The rule lives in one place — visible_tickets() in app/routers/tickets.py —
and every read and write path builds on it. These tests exercise that rule
from the outside, through each endpoint that must honor it, and check the
two properties that make it a security control rather than a convenience:
out-of-scope tickets return 404 (not 403), and filters can only narrow the
visible set, never widen it.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login, make_user


def create_ticket(client, title="Someone's ticket"):
    response = client.post("/tickets", json={"title": title})
    assert response.status_code == 201
    return response.json()


def client_for(db, email, is_admin=False):
    """Create a user and return (user, authenticated client) for it.

    Tests here need more principals than the conftest fixtures provide (a
    stranger, an agent). The TestClient is used without the context manager
    because the app has no startup hooks these requests depend on; the
    conftest fixtures use `with` for symmetry with production lifecycle.
    """
    user = make_user(db, email, is_admin=is_admin)
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {login(c, email)}"})
    return user, c


# --- Strangers --------------------------------------------------------------


def test_other_users_tickets_are_invisible(authed_client, db):
    made = create_ticket(authed_client)
    _, stranger = client_for(db, "stranger@example.com")

    # The list is empty rather than filtered client-side...
    assert stranger.get("/tickets").json()["total"] == 0
    # ...and direct access by id is 404 on every read and write path. Not
    # 403: a forbidden response would confirm the id exists, letting an
    # attacker enumerate tickets.
    assert stranger.get(f"/tickets/{made['id']}").status_code == 404
    assert stranger.get(f"/tickets/{made['id']}/audit").status_code == 404
    assert stranger.post(f"/tickets/{made['id']}/comments", json={"body": "hi"}).status_code == 404
    assert stranger.patch(f"/tickets/{made['id']}", json={"priority": 1}).status_code == 404


def test_filters_cannot_widen_scope(authed_client, admin_client, admin_user, db):
    # Filters are applied on top of the scoped query. Naming another user's
    # id in owner_id or assignee_id must not reveal their tickets.
    create_ticket(admin_client, title="Admin's private ticket")
    _, stranger = client_for(db, "stranger@example.com")

    assert stranger.get("/tickets", params={"owner_id": admin_user.id}).json()["total"] == 0
    assert stranger.get("/tickets", params={"assignee_id": admin_user.id}).json()["total"] == 0
    assert stranger.get("/tickets", params={"q": "private"}).json()["total"] == 0


# --- Owners and assignees ---------------------------------------------------


def test_scope_is_owned_or_assigned(authed_client, admin_client, test_user, db):
    # A regular user's list is the union of tickets they opened and tickets
    # assigned to them — and nothing else.
    create_ticket(authed_client, title="Mine")
    assigned = create_ticket(admin_client, title="Assigned to me")
    create_ticket(admin_client, title="Not mine")
    admin_client.patch(f"/tickets/{assigned['id']}", json={"assignee_id": test_user.id})

    titles = {t["title"] for t in authed_client.get("/tickets").json()["items"]}
    assert titles == {"Mine", "Assigned to me"}


def test_assignee_can_see_and_work_ticket(authed_client, admin_client, db):
    made = create_ticket(authed_client)
    agent, agent_client = client_for(db, "agent@example.com")
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": agent.id})

    # Being assigned grants visibility on every read path...
    assert agent_client.get(f"/tickets/{made['id']}").status_code == 200
    assert agent_client.get(f"/tickets/{made['id']}/audit").status_code == 200
    # ...and the rights needed to work the ticket: status changes and comments.
    response = agent_client.patch(f"/tickets/{made['id']}", json={"status": "in_progress"})
    assert response.status_code == 200
    assert agent_client.post(f"/tickets/{made['id']}/comments", json={"body": "On it."}).status_code == 201
    # But assignment itself is a triage power and stays admin-only — an agent
    # can neither hand the ticket off nor unassign themselves.
    assert agent_client.patch(f"/tickets/{made['id']}", json={"assignee_id": None}).status_code == 403


def test_unassigning_revokes_visibility(authed_client, admin_client, db):
    # Visibility is evaluated on every request from the current assignment,
    # so removing the assignee takes effect immediately.
    made = create_ticket(authed_client)
    agent, agent_client = client_for(db, "agent@example.com")
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": agent.id})
    assert agent_client.get(f"/tickets/{made['id']}").status_code == 200

    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": None})
    assert agent_client.get(f"/tickets/{made['id']}").status_code == 404
    assert agent_client.get("/tickets").json()["total"] == 0


# --- Admins -----------------------------------------------------------------


def test_admin_sees_all_tickets(authed_client, admin_client):
    made = create_ticket(authed_client)
    assert admin_client.get(f"/tickets/{made['id']}").status_code == 200
    assert admin_client.get("/tickets").json()["total"] == 1


def test_owner_filter(authed_client, admin_client, test_user):
    # For admins, who see everything, owner_id is a genuine filter.
    create_ticket(authed_client, title="Mine")
    create_ticket(admin_client, title="Admin's")

    response = admin_client.get("/tickets", params={"owner_id": test_user.id})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Mine"
