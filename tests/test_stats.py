def create_ticket(client, **overrides):
    payload = {"title": "Stats ticket"}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def test_stats_counts(authed_client):
    create_ticket(authed_client, priority=1)
    in_progress = create_ticket(authed_client)
    authed_client.patch(f"/tickets/{in_progress['id']}", json={"status": "in_progress"})
    resolved = create_ticket(authed_client)
    authed_client.patch(f"/tickets/{resolved['id']}", json={"status": "resolved"})

    stats = authed_client.get("/tickets/stats").json()
    assert stats["total"] == 3
    assert stats["by_status"] == {"new": 1, "open": 0, "in_progress": 1, "resolved": 1, "closed": 0}
    assert stats["unresolved"] == 2
    assert stats["p1_unresolved"] == 1
    assert stats["unassigned_unresolved"] == 2
    assert stats["overdue"] == 0  # nothing past its SLA yet
    assert stats["avg_resolution_hours"] is not None  # one resolved ticket


def test_stats_scoped_to_visible_tickets(authed_client, admin_client):
    create_ticket(authed_client)
    create_ticket(admin_client)

    # Each regular user counts only their own; the admin counts everything.
    assert authed_client.get("/tickets/stats").json()["total"] == 1
    assert admin_client.get("/tickets/stats").json()["total"] == 2


def test_stats_requires_auth(client):
    assert client.get("/tickets/stats").status_code == 401
