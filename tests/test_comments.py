"""Comments: author always comes from the token, bodies are validated,
comments are read back in order on the ticket, and the visibility rule
gates who may comment.

Cross-user visibility for comments (a stranger gets 404, an assignee may
comment) is covered in test_visibility.py.
"""


def make_ticket(client, **overrides):
    payload = {"title": "Needs discussion"}
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_comment(client, ticket_id, body):
    return client.post(f"/tickets/{ticket_id}/comments", json={"body": body})


# --- Creating comments ------------------------------------------------------


def test_comment_author_comes_from_token(authed_client, test_user):
    # Mass-assignment defense, same principle as ticket ownership: a client
    # naming another author_id in the body is ignored.
    ticket = make_ticket(authed_client)
    response = authed_client.post(
        f"/tickets/{ticket['id']}/comments",
        json={"body": "Checked the switch, all ports green.", "author_id": 999},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["author"]["id"] == test_user.id
    assert body["body"] == "Checked the switch, all ports green."
    # Timestamps carry an explicit UTC offset; the nested author is the
    # public user shape only.
    assert body["created_at"].endswith(("Z", "+00:00"))
    assert "hashed_password" not in body["author"]


def test_admin_can_comment_on_any_ticket(authed_client, admin_client, admin_user):
    ticket = make_ticket(authed_client)
    response = add_comment(admin_client, ticket["id"], "Triaged; assigning shortly.")
    assert response.status_code == 201
    assert response.json()["author"]["id"] == admin_user.id


def test_comments_allowed_on_closed_tickets(authed_client):
    # Closing ends the workflow, not the conversation: a follow-up note on a
    # closed ticket (root cause, "happened again") is legitimate.
    ticket = make_ticket(authed_client)
    for status in ("resolved", "closed"):
        assert authed_client.patch(f"/tickets/{ticket['id']}", json={"status": status}).status_code == 200
    assert add_comment(authed_client, ticket["id"], "Root cause was a bad cable.").status_code == 201


# --- Reading comments back --------------------------------------------------


def test_comments_are_returned_in_chronological_order(authed_client):
    # The ticket detail embeds comments ordered by created_at (the
    # relationship's order_by), so a thread reads top to bottom.
    ticket = make_ticket(authed_client)
    for text in ("First", "Second", "Third"):
        assert add_comment(authed_client, ticket["id"], text).status_code == 201

    detail = authed_client.get(f"/tickets/{ticket['id']}").json()
    assert [c["body"] for c in detail["comments"]] == ["First", "Second", "Third"]


# --- Validation and errors --------------------------------------------------


def test_comment_on_missing_ticket_404(authed_client):
    response = authed_client.post("/tickets/9999/comments", json={"body": "Hello?"})
    assert response.status_code == 404


def test_comment_requires_auth(client):
    response = client.post("/tickets/1/comments", json={"body": "Anonymous"})
    assert response.status_code == 401


def test_empty_comment_rejected(authed_client):
    ticket = make_ticket(authed_client)
    assert add_comment(authed_client, ticket["id"], "").status_code == 422


def test_overlong_comment_rejected(authed_client):
    # 5,000-character cap (schemas.CommentCreate); rejected by validation
    # before the handler runs, so nothing is stored.
    ticket = make_ticket(authed_client)
    assert add_comment(authed_client, ticket["id"], "x" * 5_001).status_code == 422
    assert authed_client.get(f"/tickets/{ticket['id']}").json()["comments"] == []
