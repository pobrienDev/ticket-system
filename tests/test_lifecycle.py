from app import models


def create_ticket(client, **overrides):
    payload = {"title": "Lifecycle ticket", "description": "Testing status transitions."}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, ticket_id, status):
    return client.patch(f"/tickets/{ticket_id}", json={"status": status})


def test_new_ticket_starts_as_new(authed_client):
    assert create_ticket(authed_client)["status"] == "new"


def test_legal_transition_chain(authed_client):
    made = create_ticket(authed_client)
    for status in ("open", "in_progress", "resolved", "closed"):
        response = set_status(authed_client, made["id"], status)
        assert response.status_code == 200, f"{status}: {response.text}"
        assert response.json()["status"] == status


def test_illegal_transitions_rejected(authed_client):
    made = create_ticket(authed_client)
    set_status(authed_client, made["id"], "resolved")

    # resolved can only be reopened or closed, never pulled back to in_progress
    response = set_status(authed_client, made["id"], "in_progress")
    assert response.status_code == 409
    assert "resolved" in response.json()["detail"]

    set_status(authed_client, made["id"], "closed")
    # closed tickets must be reopened first
    for status in ("in_progress", "resolved"):
        assert set_status(authed_client, made["id"], status).status_code == 409
    assert set_status(authed_client, made["id"], "open").status_code == 200


def test_resolved_at_stamped_and_cleared_on_reopen(authed_client):
    made = create_ticket(authed_client)
    resolved = set_status(authed_client, made["id"], "resolved").json()
    assert resolved["resolved_at"] is not None

    reopened = set_status(authed_client, made["id"], "open").json()
    assert reopened["resolved_at"] is None


def test_closing_a_resolved_ticket_keeps_resolved_at(authed_client):
    # resolved -> closed is completion, not a reopen: the resolution
    # timestamp must survive (stats' avg resolution depends on it).
    made = create_ticket(authed_client)
    resolved = set_status(authed_client, made["id"], "resolved").json()
    closed = set_status(authed_client, made["id"], "closed").json()
    assert closed["resolved_at"] == resolved["resolved_at"]

    # And the closed ticket still counts toward average resolution time.
    stats = authed_client.get("/tickets/stats").json()
    assert stats["avg_resolution_hours"] is not None


def test_due_date_follows_priority_sla(authed_client):
    import datetime

    p1 = create_ticket(authed_client, priority=1)
    p5 = create_ticket(authed_client, priority=5)
    p1_due = datetime.datetime.fromisoformat(p1["due_date"])
    p5_due = datetime.datetime.fromisoformat(p5["due_date"])
    p1_created = datetime.datetime.fromisoformat(p1["created_at"])
    assert p1_due - p1_created == datetime.timedelta(hours=models.SLA_HOURS[1])
    assert p5_due > p1_due


def test_priority_and_title_changes_are_audited(authed_client, db):
    made = create_ticket(authed_client, title="Before", priority=3)
    authed_client.patch(f"/tickets/{made['id']}", json={"priority": 1, "title": "After"})

    entries = {
        e.field: e for e in db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).all()
    }
    assert entries["priority"].old_value == "P3" and entries["priority"].new_value == "P1"
    assert entries["title"].old_value == "Before" and entries["title"].new_value == "After"


def test_noop_patch_writes_no_audit(authed_client, db):
    made = create_ticket(authed_client, priority=2)
    response = authed_client.patch(f"/tickets/{made['id']}", json={"priority": 2})
    assert response.status_code == 200
    assert db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).count() == 0
