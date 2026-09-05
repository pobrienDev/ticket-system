"""SQLAlchemy ORM models — the persistent shape of the domain.

Domain rules that belong with the data (the status transition map and SLA
targets) also live here rather than in the HTTP layer, so they can be reused
by routers, the seed script, and tests alike.

These classes describe what the database stores. What the API accepts and
returns is a separate concern, defined in schemas.py.
"""

import datetime
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, TypeDecorator
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class UTCDateTime(TypeDecorator):
    """Always store and return timezone-aware UTC datetimes.

    SQLite drops tzinfo on write and returns naive datetimes; without this the
    API would serialize timestamps with no offset and clients would misparse
    them as local time. Postgres (timestamptz) is unaffected either way.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(datetime.timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value


class TicketStatus(str, enum.Enum):
    new = "new"  # just created, not yet triaged
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


# Legal status transitions. A ticket starts as `new`; resolved/closed tickets
# must be reopened (back to `open`) before they can move anywhere else.
ALLOWED_TRANSITIONS = {
    TicketStatus.new: {
        TicketStatus.open, TicketStatus.in_progress, TicketStatus.resolved, TicketStatus.closed
    },
    TicketStatus.open: {TicketStatus.in_progress, TicketStatus.resolved, TicketStatus.closed},
    TicketStatus.in_progress: {TicketStatus.open, TicketStatus.resolved, TicketStatus.closed},
    TicketStatus.resolved: {TicketStatus.open, TicketStatus.closed},
    TicketStatus.closed: {TicketStatus.open},
}

# Response-time targets by priority (1 = highest), used to stamp due_date on create.
SLA_HOURS = {1: 4, 2: 24, 3: 72, 4: 168, 5: 336}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    tickets = relationship("Ticket", back_populates="category")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, default="", server_default="", nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.new, nullable=False, index=True)
    priority = Column(Integer, default=3, nullable=False)  # 1 = highest
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    due_date = Column(UTCDateTime, nullable=True)  # SLA target, derived from priority on create
    resolved_at = Column(UTCDateTime, nullable=True)  # stamped on entering resolved, cleared on reopen
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
    here except the cascade when a ticket itself is deleted.
    """

    __tablename__ = "audit_log_entries"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    field = Column(String, nullable=False)  # e.g. "status", "assignee"
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="audit_log")
    actor = relationship("User")
