"""Status lifecycle rules, resolved_at bookkeeping, SLA due dates, and audit
coverage of the non-status fields.

The lifecycle is defined once, in models.ALLOWED_TRANSITIONS, and enforced in
update_ticket. The exhaustive transition test below is generated from that
map, so the map and the tests cannot drift apart.
"""

import datetime

import pytest

from app import models

STATUSES = [s.value for s in models.TicketStatus]

# A legal path from `new` to each status, used to put a ticket into a known
# starting state. Every step here is itself an allowed transition.
PATH_TO = {
    "new": [],
    "open": ["open"],
    "in_progress": ["in_progress"],
    "resolved": ["resolved"],
    "closed": ["resolved", "closed"],
}


def create_ticket(client, **overrides):
    payload = {"title": "Lifecycle ticket", "description": "Testing status transitions."}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, ticket_id, status):
    return client.patch(f"/tickets/{ticket_id}", json={"status": status})


def drive_to(client, ticket_id, status):
    """Move a fresh ticket to `status` through known-legal steps."""
    for step in PATH_TO[status]:
        response = set_status(client, ticket_id, step)
        assert response.status_code == 200, f"setup step {step}: {response.text}"


# --- Transitions ------------------------------------------------------------


def test_new_ticket_starts_as_new(authed_client):
    # Tickets enter the queue untriaged; nothing is "open" until someone looks.
    assert create_ticket(authed_client)["status"] == "new"


def test_legal_transition_chain(authed_client):
    # The canonical happy path, end to end.
    made = create_ticket(authed_client)
    for status in ("open", "in_progress", "resolved", "closed"):
        response = set_status(authed_client, made["id"], status)
        assert response.status_code == 200, f"{status}: {response.text}"
        assert response.json()["status"] == status


@pytest.mark.parametrize(
    ("start", "target"),
    [(s, t) for s in STATUSES for t in STATUSES if s != t],
)
def test_every_transition_matches_the_map(authed_client, start, target):
    # Executable specification of ALLOWED_TRANSITIONS: for every ordered pair
    # of distinct statuses, the API must allow exactly what the map allows.
    made = create_ticket(authed_client)
    drive_to(authed_client, made["id"], start)

    response = set_status(authed_client, made["id"], target)
    allowed = models.TicketStatus(target) in models.ALLOWED_TRANSITIONS[models.TicketStatus(start)]
    if allowed:
        assert response.status_code == 200, f"{start} -> {target} should be legal: {response.text}"
        assert response.json()["status"] == target
    else:
        # 409: well-formed and authorized, but conflicts with current state.
        assert response.status_code == 409, f"{start} -> {target} should be illegal"
        assert start in response.json()["detail"] and target in response.json()["detail"]


def test_illegal_transitions_rejected(authed_client):
    # A readable walk through the two rules people ask about most.
    made = create_ticket(authed_client)
    assert set_status(authed_client, made["id"], "resolved").status_code == 200

    # resolved can only be reopened or closed, never pulled back to in_progress
    response = set_status(authed_client, made["id"], "in_progress")
    assert response.status_code == 409
    assert "resolved" in response.json()["detail"]

    assert set_status(authed_client, made["id"], "closed").status_code == 200
    # closed tickets must be reopened first
    for status in ("in_progress", "resolved"):
        assert set_status(authed_client, made["id"], status).status_code == 409
    assert set_status(authed_client, made["id"], "open").status_code == 200


def test_setting_the_same_status_is_a_noop(authed_client, db):
    # The map has no self-transitions, but re-sending the current status is
    # not an illegal move: it is simply no change (200, nothing audited).
    made = create_ticket(authed_client)
    response = set_status(authed_client, made["id"], "new")
    assert response.status_code == 200
    assert response.json()["status"] == "new"
    assert db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).count() == 0


# --- resolved_at ------------------------------------------------------------


def test_resolved_at_stamped_and_cleared_on_reopen(authed_client):
    made = create_ticket(authed_client)
    resolved = set_status(authed_client, made["id"], "resolved").json()
    assert resolved["resolved_at"] is not None

    reopened = set_status(authed_client, made["id"], "open").json()
    assert reopened["resolved_at"] is None


def test_closing_a_resolved_ticket_keeps_resolved_at(authed_client):
    # Regression test. resolved -> closed is completion, not a reopen: the
    # resolution timestamp must survive (stats' avg resolution depends on it).
    # The original guard checked the ticket's OLD status and wiped the
    # timestamp on this exact path.
    made = create_ticket(authed_client)
    resolved = set_status(authed_client, made["id"], "resolved").json()
    closed = set_status(authed_client, made["id"], "closed").json()
    assert closed["resolved_at"] == resolved["resolved_at"]

    # And the closed ticket still counts toward average resolution time.
    stats = authed_client.get("/tickets/stats").json()
    assert stats["avg_resolution_hours"] is not None


def test_reopening_a_closed_ticket_clears_resolved_at(authed_client):
    # closed -> open is a reopen: the ticket is back in the queue and has no
    # resolution time until it is resolved again.
    made = create_ticket(authed_client)
    drive_to(authed_client, made["id"], "closed")
    assert authed_client.get(f"/tickets/{made['id']}").json()["resolved_at"] is not None

    reopened = set_status(authed_client, made["id"], "open").json()
    assert reopened["resolved_at"] is None


# --- SLA due dates ----------------------------------------------------------


@pytest.mark.parametrize("priority", sorted(models.SLA_HOURS))
def test_due_date_follows_priority_sla(authed_client, priority):
    # due_date is created_at + the SLA for the priority, computed from the
    # same timestamp so the difference is exact, not off by microseconds.
    made = create_ticket(authed_client, priority=priority)
    due = datetime.datetime.fromisoformat(made["due_date"])
    created = datetime.datetime.fromisoformat(made["created_at"])
    assert due - created == datetime.timedelta(hours=models.SLA_HOURS[priority])


def test_higher_priority_means_sooner_due_date(authed_client):
    p1 = create_ticket(authed_client, priority=1)
    p5 = create_ticket(authed_client, priority=5)
    assert datetime.datetime.fromisoformat(p1["due_date"]) < datetime.datetime.fromisoformat(p5["due_date"])


# --- Audit of non-status fields --------------------------------------------


def test_priority_and_title_changes_are_audited(authed_client, db):
    made = create_ticket(authed_client, title="Before", priority=3)
    authed_client.patch(f"/tickets/{made['id']}", json={"priority": 1, "title": "After"})

    entries = {
        e.field: e for e in db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).all()
    }
    # Priority is logged in the human form the UI shows, not as a bare integer.
    assert entries["priority"].old_value == "P3" and entries["priority"].new_value == "P1"
    assert entries["title"].old_value == "Before" and entries["title"].new_value == "After"


def test_description_audit_is_clipped(authed_client, db):
    # Audit values are for reading history, not replaying it: long text is
    # clipped to 120 characters so description edits can't bloat the table.
    made = create_ticket(authed_client)
    long_text = "x" * 500
    authed_client.patch(f"/tickets/{made['id']}", json={"description": long_text})

    entry = db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"], field="description").one()
    assert entry.old_value == made["description"]
    assert len(entry.new_value) == 120
    assert entry.new_value.endswith("...")
    # The ticket itself keeps the full text.
    assert authed_client.get(f"/tickets/{made['id']}").json()["description"] == long_text


def test_category_change_is_audited_by_name(authed_client, category, db):
    # Category is logged by name (not id) in both directions, including
    # clearing it, so the history reads as prose.
    made = create_ticket(authed_client)
    authed_client.patch(f"/tickets/{made['id']}", json={"category_id": category.id})
    authed_client.patch(f"/tickets/{made['id']}", json={"category_id": None})

    entries = (
        db.query(models.AuditLogEntry)
        .filter_by(ticket_id=made["id"], field="category")
        .order_by(models.AuditLogEntry.id)
        .all()
    )
    assert [(e.old_value, e.new_value) for e in entries] == [(None, "Network"), ("Network", None)]


def test_noop_patch_writes_no_audit(authed_client, db):
    # Re-sending a field's current value is not a change and must not create
    # a history entry.
    made = create_ticket(authed_client, priority=2)
    response = authed_client.patch(f"/tickets/{made['id']}", json={"priority": 2})
    assert response.status_code == 200
    assert db.query(models.AuditLogEntry).filter_by(ticket_id=made["id"]).count() == 0
