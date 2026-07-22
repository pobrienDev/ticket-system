import logging
import os

import httpx

logger = logging.getLogger(__name__)

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailAPIError(Exception):
    """Raised when the email provider rejects or fails a send."""


def send_email(to: str, subject: str, body: str) -> None:
    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("EMAIL_FROM", "tickets@example.com")

    if not api_key:
        # Console backend for local development: no key, no network call.
        logger.info("SENDGRID_API_KEY not set; would send to %s: %s — %s", to, subject, body)
        return

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    try:
        response = httpx.post(
            SENDGRID_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmailAPIError(str(exc)) from exc


def notify_assignment(ticket, assignee_email: str) -> None:
    try:
        send_email(
            to=assignee_email,
            subject=f"Ticket #{ticket.id} assigned to you",
            body=f"'{ticket.title}' has been assigned to you.",
        )
    except EmailAPIError as exc:
        # Log and continue — a notification failure should never
        # block the actual ticket assignment from succeeding.
        logger.warning("Email notification failed for ticket %s: %s", ticket.id, exc)
