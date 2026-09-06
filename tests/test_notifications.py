"""Assignment emails.

Two layers are tested separately:

* send_email — the SendGrid call itself, with httpx.post mocked so the
  request shape, the console fallback, and provider failures are verified
  without any network access.
* notify_assignment and the PATCH endpoint — mocked at send_email (not at
  notify_assignment) so the real never-fatal error handling runs.

conftest sets SENDGRID_API_KEY to an empty string, so unless a test sets a
key explicitly, send_email takes the console path.
"""

import logging
from unittest.mock import patch

import httpx

from app.notifications import EmailAPIError, notify_assignment, send_email


class FakeTicket:
    # notify_assignment only reads id and title; a stub avoids a database
    # round-trip for the unit tests below.
    id = 42
    title = "Router replacement"


# --- send_email: the provider call ------------------------------------------


def test_send_email_without_api_key_logs_instead_of_sending(caplog):
    # Console backend: no key means no network call at all — dev and CI need
    # no credentials — and the would-be message is logged for visibility.
    with patch("app.notifications.httpx.post") as mock_post:
        with caplog.at_level(logging.INFO, logger="app.notifications"):
            send_email(to="tech@example.com", subject="Hello", body="World")
    mock_post.assert_not_called()
    assert any("would send to tech@example.com" in m for m in caplog.messages)


def test_send_email_with_api_key_posts_expected_request(monkeypatch):
    monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
    monkeypatch.setenv("EMAIL_FROM", "helpdesk@example.com")

    with patch("app.notifications.httpx.post") as mock_post:
        send_email(to="tech@example.com", subject="Ticket #42 assigned to you", body="Details")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.sendgrid.com/v3/mail/send"
    # The key travels only in the Authorization header, never in the body.
    assert kwargs["headers"]["Authorization"] == "Bearer sg-test-key"
    payload = kwargs["json"]
    assert payload["personalizations"] == [{"to": [{"email": "tech@example.com"}]}]
    assert payload["from"] == {"email": "helpdesk@example.com"}
    assert payload["subject"] == "Ticket #42 assigned to you"
    assert payload["content"] == [{"type": "text/plain", "value": "Details"}]
    # A bounded timeout so a hung provider can't hold a worker indefinitely.
    assert kwargs["timeout"] == 10


def test_send_email_wraps_provider_errors(monkeypatch):
    # Every httpx failure — a 5xx response or a transport error — surfaces as
    # one EmailAPIError, so callers never need to know about httpx.
    monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")

    with patch("app.notifications.httpx.post") as mock_post:
        mock_post.return_value.raise_for_status.side_effect = httpx.HTTPError("503 Service Unavailable")
        try:
            send_email(to="tech@example.com", subject="s", body="b")
        except EmailAPIError as exc:
            assert "503" in str(exc)
        else:
            raise AssertionError("expected EmailAPIError for a 5xx response")

    with patch("app.notifications.httpx.post", side_effect=httpx.ConnectError("dns failure")):
        try:
            send_email(to="tech@example.com", subject="s", body="b")
        except EmailAPIError as exc:
            assert "dns failure" in str(exc)
        else:
            raise AssertionError("expected EmailAPIError for a transport error")


# --- notify_assignment: the never-fatal wrapper ----------------------------


def test_notify_assignment_swallows_email_failure(caplog):
    # Design rule: a notification failure is logged and never propagates, so
    # it can't break the assignment that triggered it.
    with patch("app.notifications.send_email", side_effect=EmailAPIError("SendGrid 503")):
        with caplog.at_level(logging.WARNING):
            notify_assignment(FakeTicket(), "tech@example.com")  # must not raise
    assert any("Email notification failed" in message for message in caplog.messages)


def test_notify_assignment_sends_expected_email():
    with patch("app.notifications.send_email") as mock_send:
        notify_assignment(FakeTicket(), "tech@example.com")
    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == "tech@example.com"
    assert "Ticket #42" in kwargs["subject"]
    assert "Router replacement" in kwargs["body"]


# --- Through the API --------------------------------------------------------


def test_assignment_sends_one_email_to_the_new_assignee(authed_client, admin_client, test_user):
    made = authed_client.post("/tickets", json={"title": "Needs an owner"}).json()
    with patch("app.notifications.send_email") as mock_send:
        response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 200
    # Runs as a background task after the commit; TestClient executes
    # background tasks before returning, so it has completed here.
    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == test_user.email
    assert f"Ticket #{made['id']}" in kwargs["subject"]


def test_no_email_unless_the_assignee_actually_changes(authed_client, admin_client, test_user):
    made = authed_client.post("/tickets", json={"title": "Quiet changes"}).json()
    admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})

    with patch("app.notifications.send_email") as mock_send:
        # Re-sending the same assignee, changing other fields, and unassigning
        # are not new assignments; none of them notifies anyone.
        admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
        admin_client.patch(f"/tickets/{made['id']}", json={"status": "in_progress", "priority": 1})
        admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": None})
    mock_send.assert_not_called()


def test_assignment_endpoint_survives_email_failure(authed_client, admin_client, test_user):
    made = authed_client.post("/tickets", json={"title": "Email raises inside"}).json()
    # Patch send_email (not notify_assignment) so the real error handling runs.
    with patch("app.notifications.send_email", side_effect=EmailAPIError("boom")):
        response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 200
    assert response.json()["assignee"]["id"] == test_user.id
