"""Comments: author always comes from the token; missing tickets and empty bodies rejected."""


def make_ticket(client):
    response = client.post("/tickets", json={"title": "Needs discussion"})
    assert response.status_code == 201
    return response.json()


def test_comment_author_comes_from_token(authed_client, test_user):
    ticket = make_ticket(authed_client)
    response = authed_client.post(
        f"/tickets/{ticket['id']}/comments",
        json={"body": "Checked the switch, all ports green.", "author_id": 999},
    )
    assert response.status_code == 201
    assert response.json()["author"]["id"] == test_user.id


def test_comment_on_missing_ticket_404(authed_client):
    response = authed_client.post("/tickets/9999/comments", json={"body": "Hello?"})
    assert response.status_code == 404


def test_comment_requires_auth(client):
    response = client.post("/tickets/1/comments", json={"body": "Anonymous"})
    assert response.status_code == 401


def test_empty_comment_rejected(authed_client):
    ticket = make_ticket(authed_client)
    response = authed_client.post(f"/tickets/{ticket['id']}/comments", json={"body": ""})
    assert response.status_code == 422
