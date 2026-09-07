"""SQLAlchemy ORM models — the persistent shape of the domain.

Domain rules that belong with the data (the status vocabulary, the transition
map, what "unresolved" means, and SLA targets) also live here rather than in
the HTTP layer, so routers, the seed script, the stats endpoint, and tests
all share one definition.

These classes describe what the database stores. What the API accepts and
returns is a separate concern, defined in schemas.py.
"""

import datetime
import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    """Timezone-aware UTC now — the only clock the app uses for stamps."""
    return datetime.datetime.now(datetime.timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store and return timezone-aware UTC datetimes on every database.

    SQLite has no timezone-aware type: it drops tzinfo on write and returns
    naive datetimes on read. Without this decorator the API would serialize
    timestamps with no offset and JavaScript clients would misparse them as
    local time. Postgres (timestamptz) is unaffected either way, so the same
    model works on both.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Normalize to UTC on the way in; treat a naive datetime as UTC."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(datetime.timezone.utc)

    def process_result_value(self, value, dialect):
        """Re-attach UTC on the way out if the driver returned a naive value."""
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value


class TicketStatus(str, enum.Enum):
    """The ticket lifecycle. The `str` mixin makes members compare equal to
    their string values and serialize as plain strings in JSON."""

    new = "new"  # just created, not yet triaged
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


# Legal status transitions. A ticket starts as `new`; resolved/closed tickets
# must be reopened (back to `open`) before they can move anywhere else.
# Enforced in routers/tickets.py (409 on an illegal move) and mirrored in
# the client's constants.js; both suites test against this map.
ALLOWED_TRANSITIONS = {
    TicketStatus.new: {
        TicketStatus.open, TicketStatus.in_progress, TicketStatus.resolved, TicketStatus.closed
    },
    TicketStatus.open: {TicketStatus.in_progress, TicketStatus.resolved, TicketStatus.closed},
    TicketStatus.in_progress: {TicketStatus.open, TicketStatus.resolved, TicketStatus.closed},
    TicketStatus.resolved: {TicketStatus.open, TicketStatus.closed},
    TicketStatus.closed: {TicketStatus.open},
}

# "Unresolved" = still needs someone's attention. Drives the stats tiles
# (unresolved, P1, unassigned, overdue) and the overdue rule: a finished
# ticket can never be late.
UNRESOLVED_STATUSES = (TicketStatus.new, TicketStatus.open, TicketStatus.in_progress)

# Response-time targets by priority (1 = highest), used to stamp due_date
# on create: a P1 is due in 4 hours, a P5 in two weeks.
SLA_HOURS = {1: 4, 2: 24, 3: 72, 4: 168, 5: 336}
PRIORITY_MIN, PRIORITY_MAX = min(SLA_HOURS), max(SLA_HOURS)


class User(Base):
    """An account. The single `is_admin` flag is the whole role model:
    admins triage (assign, delete, manage categories) and see every ticket;
    everyone else sees only tickets they own or are assigned to."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    # Stored lowercased (see routers/users.py) so the unique index makes
    # Joyce@ and joyce@ the same account.
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)  # bcrypt; never the password itself
    is_admin = Column(Boolean, default=False, nullable=False)


class Category(Base):
    """A helpdesk queue label (Printer, Network, …). Admin-managed reference
    data, seeded with real categories; tickets may have at most one."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    tickets = relationship("Ticket", back_populates="category")


class Ticket(Base):
    """The central record. Two foreign keys point at users — the owner who
    opened it and the optional assignee working it — which is why each
    relationship below names its foreign key explicitly."""

    __tablename__ = "tickets"
    __table_args__ = (
        # Defense in depth for the one numeric field with a business range:
        # the API validates 1–5, and so does the database, so no other writer
        # (a seed script, a migration, a console session) can store a P9.
        CheckConstraint(
            f"priority BETWEEN {PRIORITY_MIN} AND {PRIORITY_MAX}", name="ck_tickets_priority_range"
        ),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, default="", server_default="", nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.new, nullable=False, index=True)
    priority = Column(Integer, default=3, nullable=False)  # 1 = highest
    # Indexed because every list query for a non-admin filters on
    # owner_id OR assignee_id, and category_id/status are the filter columns.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    due_date = Column(UTCDateTime, nullable=True)  # SLA target, derived from priority on create
    resolved_at = Column(UTCDateTime, nullable=True)  # set on entering resolved, cleared on reopen
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Two foreign keys to users: SQLAlchemy needs foreign_keys=[...] spelled
    # out so it knows which FK backs which relationship.
    owner = relationship("User", foreign_keys=[owner_id])
    assignee = relationship("User", foreign_keys=[assignee_id])
    category = relationship("Category", back_populates="tickets")
    # Comments and audit entries have no meaning without their ticket, so they
    # are deleted with it (cascade) rather than left as orphans.
    comments = relationship(
        "Comment", back_populates="ticket", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    audit_log = relationship(
        "AuditLogEntry",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="AuditLogEntry.created_at",
    )


class Comment(Base):
    """A note on a ticket. The author always comes from the request's token,
    never from the client, and comments are read back in creation order."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(String, nullable=False)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("User")


class AuditLogEntry(Base):
    """One field change on one ticket: who changed what, from what, to what.

    Append-only by convention — nothing in the app updates or deletes rows
    here except the cascade when a ticket itself is deleted. Values are
    stored as short strings (clipped by the writer) because the log is for
    people reading history, not for machine replay.
    """

    __tablename__ = "audit_log_entries"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    field = Column(String, nullable=False)  # e.g. "status", "assignee", "title"
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="audit_log")
    actor = relationship("User")
