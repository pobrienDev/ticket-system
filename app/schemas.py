"""Pydantic schemas — the API contract.

Request schemas (…Create/…Update) define what clients may send and enforce
limits before any handler code runs; response schemas (…Response) define
exactly which fields leave the server. Keeping these separate from the ORM
models means a database column is never exposed by accident (User has a
hashed_password column; no response schema mentions it).

Two properties of every request schema are deliberate and worth knowing:

* Unknown fields are ignored, not rejected. A client sending `owner_id` or
  `is_admin` in a body has it silently dropped — ownership and roles come
  from the token and the database, never from the request. (The trade-off
  is that a misspelled field is ignored rather than flagged; the OpenAPI
  docs and the frontend's single api.js module keep that risk low.)
* Length caps on text fields are part of the contract: they bound storage,
  response size, and search cost. They are defined once below and mirrored
  by maxLength attributes in the UI.
"""

import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from .auth import BCRYPT_MAX_PASSWORD_BYTES
from .models import PRIORITY_MAX, PRIORITY_MIN, TicketStatus

# --- Limits (one definition each; the UI mirrors them) ---

TITLE_MAX = 200
DESCRIPTION_MAX = 10_000
COMMENT_MAX = 5_000
CATEGORY_NAME_MAX = 100
PASSWORD_MIN = 8


def _strip_non_blank(value: str) -> str:
    """Trim surrounding whitespace, then require that something is left.

    min_length alone would accept "   " — a comment or title that is only
    whitespace, which renders as an empty bubble with an author and a time.
    """
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


# A string that is stored trimmed and can never be empty or whitespace-only.
# Used for every human-entered name/title/body that must carry content.
# Field(max_length=…) constraints run before this validator, on the raw value.
NonBlank = Annotated[str, AfterValidator(_strip_non_blank)]

# A reference to another row. Ids are positive integers; 0 or a negative
# number can never match, so it is rejected as invalid input (422) rather
# than looked up and reported as unknown (400).
RowId = Annotated[int, Field(ge=1)]


class ORMModel(BaseModel):
    """Base for response schemas built from SQLAlchemy objects.

    from_attributes lets Pydantic read model attributes (ticket.owner.email)
    instead of dict keys, so a handler can return the ORM object directly.
    """

    model_config = ConfigDict(from_attributes=True)


# --- Auth / users ---


class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt accepts at most 72 BYTES of password. max_length counts
    # characters, which is only the same thing for ASCII, so the byte length
    # is checked explicitly below — otherwise a 72-character password of
    # multi-byte characters would pass validation and fail inside bcrypt.
    password: str = Field(min_length=PASSWORD_MIN, max_length=BCRYPT_MAX_PASSWORD_BYTES)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes")
        return value


class UserResponse(ORMModel):
    # Plain str, not EmailStr: a response describes stored data, it does not
    # validate it. Re-validating on output could turn a read into a 500.
    id: int
    email: str
    is_admin: bool


class Token(BaseModel):
    """The login response, in the shape OAuth2 clients expect."""

    access_token: str
    token_type: str = "bearer"


# --- Categories ---


class CategoryCreate(BaseModel):
    name: NonBlank = Field(max_length=CATEGORY_NAME_MAX)


class CategoryResponse(ORMModel):
    id: int
    name: str


# --- Comments ---


class CommentCreate(BaseModel):
    body: NonBlank = Field(max_length=COMMENT_MAX)


class CommentResponse(ORMModel):
    id: int
    body: str
    author: UserResponse
    created_at: datetime.datetime


# --- Tickets ---


class TicketCreate(BaseModel):
    title: NonBlank = Field(max_length=TITLE_MAX)
    # Description may legitimately be empty; it is not NonBlank.
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    category_id: RowId | None = None
    priority: int = Field(default=3, ge=PRIORITY_MIN, le=PRIORITY_MAX)  # 1 = highest


class TicketUpdate(BaseModel):
    """A partial update: only fields present in the request are applied.

    The router reads this with model_dump(exclude_unset=True), so `None`
    defaults below mean "not sent", never "set to null". For the nullable
    columns (category_id, assignee_id) an explicit null IS meaningful — it
    clears the category or unassigns — and is allowed; for NOT NULL columns
    an explicit null is rejected by the validator below.
    """

    title: NonBlank | None = Field(default=None, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    status: TicketStatus | None = None
    priority: int | None = Field(default=None, ge=PRIORITY_MIN, le=PRIORITY_MAX)
    category_id: RowId | None = None
    assignee_id: RowId | None = None

    @field_validator("title", "description", "status", "priority", mode="before")
    @classmethod
    def reject_explicit_null(cls, value, info):
        # Runs only for fields present in the request; omitted fields are
        # untouched. mode="before" means it sees the raw JSON value, so the
        # null is caught before NonBlank or the enum would try to parse it.
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
    """The single-ticket view: everything in the list shape plus comments."""

    comments: list[CommentResponse]


class TicketListResponse(BaseModel):
    # Paginated envelope: `total` is the count of everything matching the
    # filters, so clients can render "showing X of Y" and know when to stop.
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


class TicketStatsResponse(BaseModel):
    """Queue health over the tickets the caller can see (see ticket_stats)."""

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
