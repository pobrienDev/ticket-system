import logging
from unittest.mock import patch

from app.notifications import EmailAPIError, notify_assignment


class FakeTicket:
    id = 42
    title = "Router replacement"


def test_notify_assignment_swallows_email_failure(caplog):
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


def test_assignment_endpoint_survives_email_failure(authed_client, admin_client, test_user):
    made = authed_client.post("/tickets", json={"title": "Email raises inside"}).json()
    # Patch send_email (not notify_assignment) so the real error handling runs.
    with patch("app.notifications.send_email", side_effect=EmailAPIError("boom")):
        response = admin_client.patch(f"/tickets/{made['id']}", json={"assignee_id": test_user.id})
    assert response.status_code == 200
    assert response.json()["assignee"]["id"] == test_user.id
