"""Outbound email via the SendGrid REST API.

Design rule for this module: notifications are a secondary concern. A failed
or slow email must never break the primary operation that triggered it, so
notify_* functions swallow provider errors (after logging) and the router
schedules them as background tasks off the request path.

Because they run after the request — and after its database session has
closed — notify_* functions take plain values (ids, strings), never ORM
objects. An ORM object handed to a background task is detached by the time
the task runs, and touching an unloaded attribute would raise.

Configuration:

* SENDGRID_API_KEY — without it, emails are logged instead of sent (the
  console backend), so development and CI need no credentials.
* EMAIL_FROM — the sender address; must be verified with SendGrid.
* APP_URL — the frontend's origin (e.g. https://tickets.example.com); when
  set, emails include a link straight to the ticket.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
# A hung provider must not hold a worker thread indefinitely.
SEND_TIMEOUT_SECONDS = 10


class EmailAPIError(Exception):
    """Raised when the email provider rejects or fails a send."""


def send_email(to: str, subject: str, body: str) -> None:
    """Send one plain-text email, raising EmailAPIError on any provider failure.

    With no API key configured this logs the message and returns — the
    console backend. Otherwise it POSTs to SendGrid and treats both transport
    failures (DNS, timeout) and rejections (4xx/5xx) as EmailAPIError, with
    the provider's explanation included so the log entry is actionable.
    """
    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("EMAIL_FROM", "tickets@example.com")

    if not api_key:
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
            timeout=SEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # SendGrid explains rejections (unverified sender, bad key) in the
        # body; a short excerpt turns "403" into something a reader can fix.
        detail = exc.response.text.strip()[:200]
        raise EmailAPIError(f"{exc} — {detail}" if detail else str(exc)) from exc
    except httpx.HTTPError as exc:
        raise EmailAPIError(str(exc)) from exc


def ticket_link(ticket_id: int) -> str | None:
    """The frontend URL for a ticket, or None when APP_URL is not configured."""
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    return f"{app_url}/#ticket-{ticket_id}" if app_url else None


def notify_assignment(ticket_id: int, title: str, assignee_email: str) -> None:
    """Email the new assignee about a ticket. Never raises.

    Scheduled by update_ticket as a background task after the assignment has
    been committed, so a slow or failing provider can neither stall the
    response nor undo the assignment. Failures are logged at WARNING.
    """
    body = f"'{title}' has been assigned to you."
    link = ticket_link(ticket_id)
    if link:
        body += f"\n\nView it: {link}"
    try:
        send_email(to=assignee_email, subject=f"Ticket #{ticket_id} assigned to you", body=body)
    except EmailAPIError as exc:
        # Log and continue — a notification failure should never
        # block the actual ticket assignment from succeeding.
        logger.warning("Email notification failed for ticket %s: %s", ticket_id, exc)
