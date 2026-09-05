"""Ticket CRUD: creation, listing/filtering/pagination, partial updates,
permissions, and the audit entries written for status and assignment."""

from app import models


def create_ticket(client, **overrides):
    payload = {"title": "Printer jams on floor 2", "description": "Paper tray 3 keeps jamming."}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_ticket_owner_comes_from_token(authed_client, test_user, other_user):
    # A client trying to claim someone else's ownership must be ignored.
    body = create_ticket(authed_client, owner_id=other_user.id)
    assert body["owner"]["id"] == test_user.id
    assert body["status"] == "new"
    assert body["priority"] == 3
    assert body["due_date"] is not None  # SLA target stamped on create
    assert body["resolved_at"] is None


def test_create_ticket_requires_auth(client):
    response = client.post("/tickets", json={"title": "No auth"})
    assert response.status_code == 401


def test_create_ticket_unknown_category_rejected(authed_client):
    response = authed_client.post("/tickets", json={"title": "Bad category", "category_id": 999})
    assert response.status_code == 400


def test_list_tickets_filters_by_status(authed_client):
    create_ticket(authed_client, title="Still new")
    made = create_ticket(authed_client, title="Resolved one")
    authed_client.patch(f"/tickets/{made['id']}", json={"status": "resolved"})

    response = authed_client.get("/tickets", params={"status": "new"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Still new"


def test_list_tickets_pagination(authed_client):
    for i in range(5):
        create_ticket(authed_client, title=f"Ticket {i}")
    response = authed_client.get("/tickets", params={"limit": 2, "offset": 2})
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_tickets_sort_by_priority(authed_client):
    create_ticket(authed_client, title="Low", priority=5)
    create_ticket(authed_client, title="Critical", priority=1)
    create_ticket(authed_client, title="Medium", priority=3)
    response = authed_client.get("/tickets", params={"sort": "priority"})
    titles = [t["title"] for t in response.json()["items"]]
    assert titles == ["Critical", "Medium", "Low"]


def test_list_tickets_search(authed_client):
    create_ticket(authed_client, title="VPN drops hourly")
    create_ticket(authed_client, title="Monitor flickers", description="The VGA cable is loose")
    response = authed_client.get("/tickets", params={"q": "vpn"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "VPN drops hourly"


def test_get_ticket_includes_comments(authed_client):
    made = create_ticket(authed_client)
    authed_client.post(f"/tickets/{made['id']}/comments", json={"body": "Tried rebooting."})
    response = authed_client.get(f"/tickets/{made['id']}")
    assert response.status_code == 200
    comments = response.json()["comments"]
    assert len(comments) == 1
    assert comments[0]["body"] == "Tried rebooting."


def test_get_missing_ticket_404(authed_client):
    assert authed_client.get("/tickets/9999").status_code == 404


def test_patch_updates_only_sent_fields(authed_client):
    made = create_ticket(authed_client, title="Original title", priority=3)
    response = authed_client.patch(f"/tickets/{made['id']}", json={"priority": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == 1
    assert body["title"] == "Original title"
    assert body["description"] == made["description"]


def test_patch_explicit_null_rejected_for_required_fields(authed_client):
    made = create_ticket(authed_client)
    for field in ("title", "description", "status", "priority"):
        response = authed_client.patch(f"/tickets/{made['id']}", json={field: None})
        assert response.status_code == 422, f"{field}: {response.text}"
    # The write must not have happened and reads must still work.
    response = authed_client.get(f"/tickets/{made['id']}")
    assert response.status_code == 200
    assert response.json()["description"] == made["description"]


def test_patch_null_assignee_unassigns(authed_client, admin_client, test_user):
    made = create_ticket(authed_client)
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": None})
    assert response.status_code == 200
    assert response.json()["assignee"] is None


def test_timestamps_are_timezone_aware(authed_client):
    made = create_ticket(authed_client)
    # Serialized timestamps must carry an explicit UTC offset so JS clients
    # don't misparse them as local time.
    assert made["created_at"].endswith(("Z", "+00:00")), made["created_at"]
    assert made["updated_at"].endswith(("Z", "+00:00")), made["updated_at"]


def test_patch_by_non_owner_denied(authed_client, admin_client, other_user, client):
    made = create_ticket(admin_client, title="Admin's ticket")
    # A ticket the user can't see 404s (not 403) so IDs can't be probed.
    response = authed_client.patch(f"/tickets/{made['id']}", json={"priority": 1})
    assert response.status_code == 404


def test_patch_by_admin_on_any_ticket_allowed(authed_client, admin_client):
    made = create_ticket(authed_client)
    response = admin_client.patch(f"/tickets/{made['id']}", json={"status": "in_progress"})
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


def test_assignment_denied_for_regular_user(authed_client, test_user):
    made = create_ticket(authed_client)
    response = authed_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 403


def test_assignment_by_admin_allowed(authed_client, admin_client, test_user):
    made = create_ticket(authed_client)
    response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 200
    assert response.json()["assignee"]["id"] == test_user.id


def test_delete_denied_for_regular_user(authed_client):
    made = create_ticket(authed_client)
    assert authed_client.delete(f"/tickets/{made['id']}").status_code == 403


def test_delete_by_admin(authed_client, admin_client):
    made = create_ticket(authed_client)
    assert admin_client.delete(f"/tickets/{made['id']}").status_code == 204
    assert authed_client.get(f"/tickets/{made['id']}").status_code == 404


def test_status_change_creates_audit_entry(authed_client, db):
    made = create_ticket(authed_client)
    authed_client.patch(f"/tickets/{made['id']}", json={"status": "in_progress"})

    entries = db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).all()
    assert len(entries) == 1
    assert entries[0].field == "status"
    assert entries[0].old_value == "new"
    assert entries[0].new_value == "in_progress"


def test_assignment_creates_audit_entry(authed_client, admin_client, test_user, db):
    made = create_ticket(authed_client)
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})

    entries = db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"], field="assignee").all()
    assert len(entries) == 1
    assert entries[0].old_value is None
    assert entries[0].new_value == test_user.email

    response = authed_client.get(f"/tickets/{made['id']}/audit")
    assert response.status_code == 200
    assert response.json()[0]["field"] == "assignee"
