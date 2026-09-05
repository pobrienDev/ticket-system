"""Pydantic schemas — the API contract.

Request schemas (…Create/…Update) define what clients may send and enforce
limits before any handler code runs; response schemas (…Response) define
exactly which fields leave the server. Keeping these separate from the ORM
models means a database column is never exposed by accident (User has a
hashed_password column; no response schema mentions it).

Length caps on text fields are a deliberate part of the contract: they bound
storage, response size, and search cost.
"""

import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import TicketStatus


class ORMModel(BaseModel):
    # from_attributes lets a response schema be built straight from a
    # SQLAlchemy object (reading attributes) instead of a dict.
    model_config = ConfigDict(from_attributes=True)


# --- Auth / users ---


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt only hashes the first 72 bytes; cap the length so two long
    # passwords sharing a prefix can't silently verify as equal.
    password: str = Field(min_length=8, max_length=72)


class UserResponse(ORMModel):
    id: int
    email: EmailStr
    is_admin: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Categories ---


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryResponse(ORMModel):
    id: int
    name: str


# --- Comments ---


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentResponse(ORMModel):
    id: int
    body: str
    author: UserResponse
    created_at: datetime.datetime


# --- Tickets ---


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    category_id: int | None = None
    priority: int = Field(default=3, ge=1, le=5)  # 1 = highest


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TicketStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    category_id: int | None = None
    assignee_id: int | None = None

    # `| None` above only means "may be omitted". These columns are NOT NULL,
    # so an explicit JSON null must be rejected, not applied. (Only runs for
    # fields actually present in the request — omitted fields are untouched.)
    @field_validator("title", "description", "status", "priority", mode="before")
    @classmethod
    def reject_explicit_null(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value


class TicketResponse(ORMModel):
    id: int
    title: str
    description: str
    status: TicketStatus
    priority: int
    owner: UserResponse
    assignee: UserResponse | None
    category: CategoryResponse | None
    due_date: datetime.datetime | None
    resolved_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class TicketDetailResponse(TicketResponse):
    comments: list[CommentResponse]


class TicketListResponse(BaseModel):
    # Paginated envelope: `total` is the count of everything matching the
    # filters, so clients can render "showing X of Y" and know when to stop.
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


class TicketStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]  # every status present, 0 when none
    unresolved: int  # new + open + in_progress
    p1_unresolved: int
    unassigned_unresolved: int
    overdue: int  # past due_date and not resolved/closed
    avg_resolution_hours: float | None  # None until something has been resolved


# --- Audit log ---


class AuditLogResponse(ORMModel):
    id: int
    field: str
    old_value: str | None
    new_value: str | None
    actor: UserResponse
    created_at: datetime.datetime
