"""Queue stats endpoint: counts, the "unresolved" qualifier, overdue detection,
average resolution time, scoping to the caller's visible tickets, and auth.

Time-dependent cases (overdue, resolution time) set due_date / created_at
directly through the db fixture, because the API never lets a client choose
those values — they are derived server-side on create and on resolve.
"""

import datetime

from app import models


def create_ticket(client, **overrides):
    payload = {"title": "Stats ticket"}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, ticket_id, status):
    response = client.patch(f"/tickets/{ticket_id}", json={"status": status})
    assert response.status_code == 200, response.text
    return response.json()


def stats_for(client):
    # This path is declared before /tickets/{ticket_id} in the router; if the
    # order ever regressed, "stats" would be parsed as an id and this would
    # come back 422 instead of 200.
    response = client.get("/tickets/stats")
    assert response.status_code == 200, response.text
    return response.json()


# --- Shape and counts -------------------------------------------------------


def test_stats_empty_queue(authed_client):
    # Zero-filled contract: every status key is present even when nothing
    # exists, and the average is None (not 0) until something has resolved.
    stats = stats_for(authed_client)
    assert stats["total"] == 0
    assert stats["by_status"] == {"new": 0, "open": 0, "in_progress": 0, "resolved": 0, "closed": 0}
    assert stats["unresolved"] == 0
    assert stats["p1_unresolved"] == 0
    assert stats["unassigned_unresolved"] == 0
    assert stats["overdue"] == 0
    assert stats["avg_resolution_hours"] is None


def test_stats_counts(authed_client):
    create_ticket(authed_client, priority=1)
    in_progress = create_ticket(authed_client)
    set_status(authed_client, in_progress["id"], "in_progress")
    resolved = create_ticket(authed_client)
    set_status(authed_client, resolved["id"], "resolved")

    stats = stats_for(authed_client)
    assert stats["total"] == 3
    assert stats["by_status"] == {"new": 1, "open": 0, "in_progress": 1, "resolved": 1, "closed": 0}
    # "unresolved" = new + open + in_progress; the resolved one is excluded.
    assert stats["unresolved"] == 2
    assert stats["p1_unresolved"] == 1
    assert stats["unassigned_unresolved"] == 2
    assert stats["overdue"] == 0  # nothing past its SLA yet
    assert stats["avg_resolution_hours"] is not None  # one resolved ticket


def test_unresolved_qualifier_excludes_finished_tickets(authed_client, admin_client, test_user):
    # A resolved P1 is not an urgent P1, and a closed unassigned ticket is
    # not waiting for an owner: both counters look only at open work.
    done_p1 = create_ticket(authed_client, priority=1)
    set_status(authed_client, done_p1["id"], "resolved")
    closed = create_ticket(authed_client)
    set_status(authed_client, closed["id"], "closed")
    live = create_ticket(authed_client, priority=1)
    admin_client.patch(f"/tickets/{live['id']}", json={"assignee_id": test_user.id})

    stats = stats_for(authed_client)
    assert stats["p1_unresolved"] == 1  # only the live P1
    assert stats["unassigned_unresolved"] == 0  # the live one is assigned; the others are finished


# --- Overdue ----------------------------------------------------------------


def test_overdue_counts_only_unresolved_tickets_past_due(authed_client, db):
    late_open = create_ticket(authed_client, title="Late and open")
    late_resolved = create_ticket(authed_client, title="Late but resolved")
    set_status(authed_client, late_resolved["id"], "resolved")
    create_ticket(authed_client, title="On time")

    # Push two tickets past their SLA. The API never lets a client do this,
    # so it is done directly in the database.
    past = models.utcnow() - datetime.timedelta(hours=1)
    for ticket_id in (late_open["id"], late_resolved["id"]):
        db.get(models.Ticket, ticket_id).due_date = past
    db.commit()

    # Only the open one is overdue: a resolved ticket cannot be late.
    assert stats_for(authed_client)["overdue"] == 1


# --- Average resolution time -----------------------------------------------


def test_avg_resolution_hours_is_the_mean_over_resolved_tickets(authed_client, db):
    # Resolve two tickets, then backdate their creation so their resolution
    # times are exactly 10h and 20h.
    ten = create_ticket(authed_client)
    set_status(authed_client, ten["id"], "resolved")
    twenty = create_ticket(authed_client)
    set_status(authed_client, twenty["id"], "resolved")
    create_ticket(authed_client)  # still open: must not affect the average

    for ticket_id, hours in ((ten["id"], 10), (twenty["id"], 20)):
        row = db.get(models.Ticket, ticket_id)
        row.created_at = row.resolved_at - datetime.timedelta(hours=hours)
    db.commit()

    assert stats_for(authed_client)["avg_resolution_hours"] == 15.0


def test_closed_tickets_still_count_toward_resolution_time(authed_client):
    # resolved -> closed keeps resolved_at (see test_lifecycle), so closing a
    # ticket must not drop it from the average.
    made = create_ticket(authed_client)
    set_status(authed_client, made["id"], "resolved")
    set_status(authed_client, made["id"], "closed")
    assert stats_for(authed_client)["avg_resolution_hours"] is not None


# --- Scoping and auth -------------------------------------------------------


def test_stats_scoped_to_visible_tickets(authed_client, admin_client, test_user):
    # Stats are computed over visible_tickets(), so each regular user sees
    # their own queue's numbers and the admin sees the whole system's.
    create_ticket(authed_client)
    assigned = create_ticket(admin_client)
    create_ticket(admin_client)
    admin_client.patch(f"/tickets/{assigned['id']}", json={"assignee_id": test_user.id})

    assert stats_for(authed_client)["total"] == 2  # owned + assigned
    assert stats_for(admin_client)["total"] == 3


def test_stats_requires_auth(client):
    assert client.get("/tickets/stats").status_code == 401
