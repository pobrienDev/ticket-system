"""Ticket CRUD: creation, listing/filtering/sorting/pagination, detail,
partial updates, permissions, deletion, and the audit entries written for
status and assignment changes.

Lifecycle rules (transition map, resolved_at) live in test_lifecycle.py;
visibility scoping between users lives in test_visibility.py.
"""

import pytest

from app import models


def create_ticket(client, **overrides):
    """POST a valid ticket and return the response body.

    Keyword overrides are merged into the payload, so a test can vary one
    field (title, priority, category_id, ...) without restating the rest.
    The status assertion here means a broken create fails loudly in setup
    rather than as a confusing KeyError later in the test.
    """
    payload = {"title": "Printer jams on floor 2", "description": "Paper tray 3 keeps jamming."}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- Create -----------------------------------------------------------------


def test_create_ticket_owner_comes_from_token(authed_client, test_user, other_user):
    # Mass-assignment defense: a client claiming someone else's ownership in
    # the body must be ignored; the owner is always the authenticated user.
    body = create_ticket(authed_client, owner_id=other_user.id)
    assert body["owner"]["id"] == test_user.id
    # Defaults applied on create: untriaged status, medium priority, an SLA
    # due date, and no resolution yet.
    assert body["status"] == "new"
    assert body["priority"] == 3
    assert body["due_date"] is not None
    assert body["resolved_at"] is None


def test_create_ticket_requires_auth(client):
    response = client.post("/tickets", json={"title": "No auth"})
    assert response.status_code == 401


def test_create_ticket_unknown_category_rejected(authed_client):
    # The id is well-formed but refers to nothing: 400, not 422.
    response = authed_client.post("/tickets", json={"title": "Bad category", "category_id": 999})
    assert response.status_code == 400


def test_create_ticket_rejects_overlong_fields(authed_client):
    # Length caps are part of the API contract (they bound storage, response
    # size, and search cost); validation rejects before the handler runs.
    response = authed_client.post("/tickets", json={"title": "t" * 201})
    assert response.status_code == 422
    response = authed_client.post("/tickets", json={"title": "ok", "description": "d" * 10_001})
    assert response.status_code == 422


# --- List: filters ----------------------------------------------------------


def test_list_tickets_filters_by_status(authed_client):
    create_ticket(authed_client, title="Still new")
    made = create_ticket(authed_client, title="Resolved one")
    assert authed_client.patch(f"/tickets/{made['id']}", json={"status": "resolved"}).status_code == 200

    response = authed_client.get("/tickets", params={"status": "new"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Still new"


def test_list_tickets_filters_by_category(authed_client, category):
    create_ticket(authed_client, title="Categorized", category_id=category.id)
    create_ticket(authed_client, title="Uncategorized")

    body = authed_client.get("/tickets", params={"category_id": category.id}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Categorized"


def test_list_tickets_filters_by_assignee(authed_client, admin_client, test_user):
    assigned = create_ticket(authed_client, title="Assigned to me")
    create_ticket(authed_client, title="Unassigned")
    admin_client.patch(f"/tickets/{assigned['id']}", json={"assignee_id": test_user.id})

    body = authed_client.get("/tickets", params={"assignee_id": test_user.id}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Assigned to me"


def test_list_tickets_search(authed_client):
    create_ticket(authed_client, title="VPN drops hourly")
    create_ticket(authed_client, title="Monitor flickers", description="The VGA cable is loose")

    # Case-insensitive: "vpn" matches a title containing "VPN".
    body = authed_client.get("/tickets", params={"q": "vpn"}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "VPN drops hourly"

    # The search covers descriptions as well as titles.
    body = authed_client.get("/tickets", params={"q": "cable"}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Monitor flickers"


# --- List: sorting and pagination ------------------------------------------


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("priority", ["Critical", "Medium", "Low"]),  # 1 = highest, so urgent first
        ("-priority", ["Low", "Medium", "Critical"]),
        ("created_at", ["Low", "Critical", "Medium"]),  # creation order
        ("-created_at", ["Medium", "Critical", "Low"]),  # the default: newest first
    ],
)
def test_list_tickets_sort_orders(authed_client, sort, expected):
    # Created in this order: Low (P5), Critical (P1), Medium (P3).
    create_ticket(authed_client, title="Low", priority=5)
    create_ticket(authed_client, title="Critical", priority=1)
    create_ticket(authed_client, title="Medium", priority=3)

    response = authed_client.get("/tickets", params={"sort": sort})
    assert response.status_code == 200
    assert [t["title"] for t in response.json()["items"]] == expected


def test_list_tickets_default_sort_is_newest_first(authed_client):
    create_ticket(authed_client, title="First")
    create_ticket(authed_client, title="Second")
    titles = [t["title"] for t in authed_client.get("/tickets").json()["items"]]
    assert titles == ["Second", "First"]


def test_list_tickets_pagination(authed_client):
    for i in range(5):
        create_ticket(authed_client, title=f"Ticket {i}")
    response = authed_client.get("/tickets", params={"limit": 2, "offset": 2})
    body = response.json()
    # total counts everything matching the filters, not just this page, so
    # a client can render "showing 2 of 5" and know when to stop.
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_tickets_rejects_invalid_query_params(authed_client):
    # sort is validated against a whitelist pattern; limit/offset have bounds.
    # All are rejected by validation (422) before any query runs.
    assert authed_client.get("/tickets", params={"sort": "title; DROP TABLE"}).status_code == 422
    assert authed_client.get("/tickets", params={"limit": 101}).status_code == 422
    assert authed_client.get("/tickets", params={"limit": 0}).status_code == 422
    assert authed_client.get("/tickets", params={"offset": -1}).status_code == 422


# --- Detail -----------------------------------------------------------------


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


def test_timestamps_are_timezone_aware(authed_client):
    made = create_ticket(authed_client)
    # Serialized timestamps must carry an explicit UTC offset so JS clients
    # don't misparse them as local time (the UTCDateTime column type
    # guarantees this on SQLite, which otherwise drops tzinfo).
    assert made["created_at"].endswith(("Z", "+00:00")), made["created_at"]
    assert made["updated_at"].endswith(("Z", "+00:00")), made["updated_at"]


# --- Update: partial-update semantics --------------------------------------


def test_patch_updates_only_sent_fields(authed_client):
    # PATCH is partial: fields omitted from the body are left untouched.
    made = create_ticket(authed_client, title="Original title", priority=3)
    response = authed_client.patch(f"/tickets/{made['id']}", json={"priority": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == 1
    assert body["title"] == "Original title"
    assert body["description"] == made["description"]


def test_patch_explicit_null_rejected_for_required_fields(authed_client):
    # "Omitted" means leave alone; an explicit null on a NOT NULL column is
    # a validation error, never applied.
    made = create_ticket(authed_client)
    for field in ("title", "description", "status", "priority"):
        response = authed_client.patch(f"/tickets/{made['id']}", json={field: None})
        assert response.status_code == 422, f"{field}: {response.text}"
    # The write must not have happened and reads must still work.
    response = authed_client.get(f"/tickets/{made['id']}")
    assert response.status_code == 200
    assert response.json()["description"] == made["description"]


def test_patch_empty_body_rejected(authed_client):
    made = create_ticket(authed_client)
    response = authed_client.patch(f"/tickets/{made['id']}", json={})
    assert response.status_code == 400


def test_patch_unknown_references_rejected(authed_client, admin_client):
    made = create_ticket(authed_client)
    assert authed_client.patch(f"/tickets/{made['id']}", json={"category_id": 999}).status_code == 400
    assert admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": 999}).status_code == 400


def test_patch_null_assignee_unassigns(authed_client, admin_client, test_user):
    # assignee_id is the one nullable field a PATCH may set to null: it means
    # "unassign", not "leave alone".
    made = create_ticket(authed_client)
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": None})
    assert response.status_code == 200
    assert response.json()["assignee"] is None


# --- Update: permissions ----------------------------------------------------


def test_patch_by_non_owner_denied(authed_client, admin_client):
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
    # Assignment is a triage power: even the ticket's owner gets 403.
    made = create_ticket(authed_client)
    response = authed_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 403


def test_assignment_by_admin_allowed(authed_client, admin_client, test_user):
    made = create_ticket(authed_client)
    response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 200
    assert response.json()["assignee"]["id"] == test_user.id


# --- Delete -----------------------------------------------------------------


def test_delete_denied_for_regular_user(authed_client):
    made = create_ticket(authed_client)
    assert authed_client.delete(f"/tickets/{made['id']}").status_code == 403


def test_delete_by_admin(authed_client, admin_client):
    made = create_ticket(authed_client)
    assert admin_client.delete(f"/tickets/{made['id']}").status_code == 204
    assert authed_client.get(f"/tickets/{made['id']}").status_code == 404


def test_delete_cascades_to_comments_and_audit(authed_client, admin_client, db):
    # Comments and audit entries have no meaning without their ticket; the
    # cascade must remove them in the same transaction (and with foreign keys
    # enforced, leaving them behind would be a constraint violation).
    made = create_ticket(authed_client)
    authed_client.post(f"/tickets/{made['id']}/comments", json={"body": "Some context."})
    authed_client.patch(f"/tickets/{made['id']}", json={"status": "in_progress"})
    assert db.query(models.Comment).filter_by(ticket_id=made["id"]).count() == 1
    assert db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).count() == 1

    assert admin_client.delete(f"/tickets/{made['id']}").status_code == 204

    assert db.query(models.Comment).filter_by(ticket_id=made["id"]).count() == 0
    assert db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).count() == 0


# --- Audit log --------------------------------------------------------------


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

    # Assignees are logged by email, not id, so the history reads as prose.
    entries = db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"], field="assignee").all()
    assert len(entries) == 1
    assert entries[0].old_value is None
    assert entries[0].new_value == test_user.email

    # The same history is readable through the API by anyone who can see the ticket.
    response = authed_client.get(f"/tickets/{made['id']}/audit")
    assert response.status_code == 200
    assert response.json()[0]["field"] == "assignee"
