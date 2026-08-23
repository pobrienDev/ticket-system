"""Idempotent seed data: real helpdesk categories, plus an optional admin user.

Run after migrations:  python -m app.seed
Set ADMIN_EMAIL and ADMIN_PASSWORD in .env to create/promote an admin account.

Add --demo to also create a realistic demo dataset (users, tickets, comments,
audit history). Demo data is only inserted into an empty ticket table, so it
never pollutes a database that already has real tickets. Demo users share the
password from DEMO_PASSWORD (default "demo1234").
"""

import argparse
import datetime
import os

from .auth import hash_password
from .database import SessionLocal
from .models import (
    SLA_HOURS,
    AuditLogEntry,
    Category,
    Comment,
    Ticket,
    TicketStatus,
    User,
    utcnow,
)

# Categories drawn from real helpdesk work.
DEFAULT_CATEGORIES = [
    "Printer",
    "Network",
    "M365/Exchange",
    "Yardi/Property Software",
    "Account Access",
    "Hardware",
]

# (email, is_admin) — admins double as the helpdesk agents so they can triage
# and be assigned; the rest are requesters.
DEMO_USERS = [
    ("sarah.chen@example.com", True),
    ("mike.torres@example.com", True),
    ("priya.patel@example.com", False),
    ("dan.kowalski@example.com", False),
    ("emma.wright@example.com", False),
]

# One row per ticket: (title, description, category, priority, status,
# owner, assignee, age_days, hours_to_resolve, [comments as (author, body)]).
# age_days spreads creation over the past month; hours_to_resolve is used for
# resolved/closed tickets. A few open/in_progress rows are older than their
# SLA on purpose so the dashboard has overdue tickets to show.
DEMO_TICKETS = [
    ("Ricoh MP C4504 jams on duplex jobs", "3rd floor copy room unit jams every duplex print; single-sided is fine. Cleared tray 2 and power cycled.", "Printer", 3, "in_progress", "priya.patel@example.com", "sarah.chen@example.com", 4, None,
     [("sarah.chen@example.com", "Duplex unit rollers look worn — ordered replacement part, ETA Thursday.")]),
    ("VPN drops every ~30 minutes on hotel wifi", "Working from a conference; AnyConnect reconnects constantly. Wired connections at the office are fine.", "Network", 2, "resolved", "dan.kowalski@example.com", "mike.torres@example.com", 9, 26,
     [("mike.torres@example.com", "Switched you to the TCP fallback gateway — captive portals throttle UDP."), ("dan.kowalski@example.com", "Stable for a full day now, thanks!")]),
    ("Shared mailbox 'leasing@' not receiving external mail", "Internal mail arrives, external senders get NDR 550 5.4.1. Started after Friday's tenant change.", "M365/Exchange", 1, "resolved", "emma.wright@example.com", "sarah.chen@example.com", 12, 6,
     [("sarah.chen@example.com", "Accepted-domain flipped to internal-relay during the tenant change. Reverted; test mail from Gmail delivered.")]),
    ("Yardi voyager report timeout on rent roll", "Rent roll for the full portfolio times out after 5 minutes. Single-property reports run fine.", "Yardi/Property Software", 2, "in_progress", "priya.patel@example.com", "mike.torres@example.com", 6, None,
     [("mike.torres@example.com", "Reproduced. Vendor ticket #48213 opened; they suspect an unindexed custom column.")]),
    ("New hire laptop setup — starts Monday", "Provision a laptop for the new leasing agent: standard image, Yardi access, desk phone.", "Hardware", 2, "closed", "emma.wright@example.com", "sarah.chen@example.com", 21, 30,
     [("sarah.chen@example.com", "Imaged and delivered to desk 14B. Yardi role pending manager approval — tracked separately.")]),
    ("Locked out of Yardi after password reset", "Reset my network password this morning and now Yardi says account disabled.", "Account Access", 2, "resolved", "dan.kowalski@example.com", "sarah.chen@example.com", 2, 3,
     [("sarah.chen@example.com", "Yardi caches the old credential — cleared the lockout and re-synced. You're in.")]),
    ("Conference room TV shows 'no signal' from laptops", "HDMI input on the big room TV stopped working; works from the Apple TV.", "Hardware", 4, "open", "emma.wright@example.com", None, 8, None, []),
    ("Outlook search returns nothing older than 30 days", "Search misses older mail in both desktop and web Outlook.", "M365/Exchange", 3, "open", "priya.patel@example.com", "mike.torres@example.com", 11, None,
     [("mike.torres@example.com", "Rebuilding the search index; if OWA is also affected it may be a mailbox indexing issue on the tenant side.")]),
    ("Guest wifi captive portal loops on Android", "Visitors on Android accept the terms and get bounced back to the portal.", "Network", 3, "open", "dan.kowalski@example.com", None, 15, None, []),
    ("Label printer offline in the mail room", "Zebra label printer shows offline; power cycling didn't help.", "Printer", 4, "closed", "emma.wright@example.com", "mike.torres@example.com", 26, 50,
     [("mike.torres@example.com", "USB cable had failed. Replaced; test labels printing.")]),
    ("Request: second monitor for accounting desk 3", "Monthly close involves a lot of spreadsheet cross-referencing; requesting a second 24\" monitor.", "Hardware", 5, "open", "priya.patel@example.com", None, 18, None, []),
    ("MFA prompt loop on new phone", "Migrated to a new phone; Authenticator now prompts endlessly and sign-in never completes.", "Account Access", 1, "in_progress", "dan.kowalski@example.com", "sarah.chen@example.com", 1, None,
     [("sarah.chen@example.com", "Cleared the stale device registration. Re-enroll from Settings > Security and reply here if the loop returns.")]),
    ("Teams calls drop when docking the laptop", "Active calls drop the moment the laptop is docked; undocked calls are stable.", "Network", 3, "new", "emma.wright@example.com", None, 0.2, None, []),
    ("Yardi check scanner rejects every batch", "Check scanner errors 'unsupported image format' on every deposit batch since this morning.", "Yardi/Property Software", 1, "new", "priya.patel@example.com", None, 0.1, None, []),
    ("Printer toner streaks on invoices", "Front-desk HP prints have a vertical gray streak; toner replaced last week.", "Printer", 4, "new", "dan.kowalski@example.com", None, 0.5, None, []),
    ("Departed employee still has mailbox access", "Contractor offboarded last month can reportedly still sign in to email.", "Account Access", 1, "closed", "emma.wright@example.com", "sarah.chen@example.com", 24, 5,
     [("sarah.chen@example.com", "Sessions revoked, account disabled, mailbox converted to shared for the manager. Flagging offboarding checklist gap.")]),
    ("Slow file transfers to the office NAS", "Copying scans to the NAS crawls at ~2 MB/s from the 2nd floor only.", "Network", 3, "resolved", "priya.patel@example.com", "mike.torres@example.com", 16, 70,
     [("mike.torres@example.com", "2nd-floor switch uplink had negotiated 100Mb. Forced gigabit; transfers now ~90 MB/s.")]),
    ("Excel crashes opening the budget workbook", "budget-2026.xlsx crashes Excel on open for everyone in finance; other files are fine.", "M365/Exchange", 2, "open", "dan.kowalski@example.com", "sarah.chen@example.com", 3, None,
     [("sarah.chen@example.com", "Opens clean in safe mode — suspecting the legacy add-in. Testing with it disabled.")]),
    ("Door badge reader offline at loading dock", "Loading dock badge reader dead; door is on manual key override.", "Hardware", 2, "open", "emma.wright@example.com", None, 5, None, []),
    ("Bulk-create tenant portal accounts for new property", "Onboarding the Maple Court property: ~60 tenant portal accounts need creation before the 1st.", "Yardi/Property Software", 3, "in_progress", "priya.patel@example.com", "mike.torres@example.com", 7, None,
     [("mike.torres@example.com", "CSV import template filled; dry run of 5 accounts succeeded. Full batch scheduled for tonight.")]),
    ("Password expiry emails going to junk", "Company password-expiry reminders land in Junk for several staff; some accounts expired unnoticed.", "M365/Exchange", 3, "resolved", "dan.kowalski@example.com", "sarah.chen@example.com", 19, 45,
     [("sarah.chen@example.com", "Added the notifier to the tenant allow list and published a DKIM record for the sending domain.")]),
    ("Fire panel modem line dead", "Monitoring company reports the fire panel's phone line stopped responding during their weekly test.", "Network", 1, "resolved", "emma.wright@example.com", "mike.torres@example.com", 14, 9,
     [("mike.torres@example.com", "Line was reprovisioned by the carrier during a port. Restored and verified with the monitoring company.")]),
    ("Scanner shortcut broken after profile migration", "Scan-to-folder from the big copier errors 'destination unreachable' since my profile was migrated.", "Printer", 4, "open", "priya.patel@example.com", None, 10, None, []),
    ("Wrong tax rate showing on lease renewals", "Renewal quotes in Yardi show last year's tax rate for two properties.", "Yardi/Property Software", 2, "new", "emma.wright@example.com", None, 0.8, None, []),
]


def seed_demo(db):
    if db.query(Ticket).count() > 0:
        print("Tickets already exist; skipping demo data.")
        return

    demo_password = os.environ.get("DEMO_PASSWORD", "demo1234")
    users = {}
    for email, is_admin in DEMO_USERS:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, hashed_password=hash_password(demo_password), is_admin=is_admin)
            db.add(user)
            print(f"Created demo user: {email}{' (agent/admin)' if is_admin else ''}")
        users[email] = user
    db.flush()

    categories = {c.name: c for c in db.query(Category).all()}
    agents = [users[email] for email, is_admin in DEMO_USERS if is_admin]
    now = utcnow()

    for i, (title, description, category, priority, status, owner, assignee, age_days, resolve_hours, comments) in enumerate(DEMO_TICKETS):
        created = now - datetime.timedelta(days=age_days)
        status = TicketStatus(status)
        agent = agents[i % len(agents)]
        resolved_at = None
        if status in (TicketStatus.resolved, TicketStatus.closed):
            resolved_at = created + datetime.timedelta(hours=resolve_hours)

        ticket = Ticket(
            title=title,
            description=description,
            status=status,
            priority=priority,
            owner_id=users[owner].id,
            assignee_id=users[assignee].id if assignee else None,
            category_id=categories[category].id if category in categories else None,
            due_date=created + datetime.timedelta(hours=SLA_HOURS[priority]),
            resolved_at=resolved_at,
            created_at=created,
            updated_at=resolved_at or (created + datetime.timedelta(hours=2) if status != TicketStatus.new else created),
        )
        db.add(ticket)
        db.flush()

        # Reconstruct a plausible history so the audit trail has something to show.
        def log(field, old, new, at):
            db.add(AuditLogEntry(
                ticket_id=ticket.id, actor_id=agent.id, field=field,
                old_value=old, new_value=new, created_at=at,
            ))

        step = created
        if assignee:
            step += datetime.timedelta(hours=1)
            log("assignee", None, assignee, step)
        for old, new in _status_path(status):
            step += datetime.timedelta(hours=1)
            log("status", old, new, min(step, resolved_at or step))

        for j, (author, body) in enumerate(comments or []):
            db.add(Comment(
                ticket_id=ticket.id,
                author_id=users[author].id,
                body=body,
                created_at=created + datetime.timedelta(hours=3 + j * 4),
            ))

    print(f"Created {len(DEMO_TICKETS)} demo tickets with comments and audit history.")


def _status_path(status):
    """The audit-log transition chain that leads to the given status."""
    paths = {
        TicketStatus.new: [],
        TicketStatus.open: [("new", "open")],
        TicketStatus.in_progress: [("new", "open"), ("open", "in_progress")],
        TicketStatus.resolved: [("new", "open"), ("open", "in_progress"), ("in_progress", "resolved")],
        TicketStatus.closed: [("new", "open"), ("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed")],
    }
    return paths[status]


def seed(demo=False):
    db = SessionLocal()
    try:
        for name in DEFAULT_CATEGORIES:
            if not db.query(Category).filter(Category.name == name).first():
                db.add(Category(name=name))
                print(f"Added category: {name}")

        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if admin_email and admin_password:
            admin_email = admin_email.lower()
            user = db.query(User).filter(User.email == admin_email).first()
            if user:
                if not user.is_admin:
                    user.is_admin = True
                    print(f"Promoted existing user to admin: {admin_email}")
            else:
                db.add(
                    User(
                        email=admin_email,
                        hashed_password=hash_password(admin_password),
                        is_admin=True,
                    )
                )
                print(f"Created admin user: {admin_email}")

        if demo:
            db.flush()
            seed_demo(db)

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="also create demo users, tickets, comments, and audit history")
    seed(demo=parser.parse_args().demo)
