import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import TicketStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth / users ---


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserResponse(ORMModel):
    id: int
    email: EmailStr
    is_admin: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Categories ---


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1)


class CategoryResponse(ORMModel):
    id: int
    name: str


# --- Comments ---


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class CommentResponse(ORMModel):
    id: int
    body: str
    author: UserResponse
    created_at: datetime.datetime


# --- Tickets ---


class TicketCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    category_id: int | None = None
    priority: int = Field(default=3, ge=1, le=5)  # 1 = highest


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
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
    created_at: datetime.datetime
    updated_at: datetime.datetime


class TicketDetailResponse(TicketResponse):
    comments: list[CommentResponse]


class TicketListResponse(BaseModel):
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


# --- Audit log ---


class AuditLogResponse(ORMModel):
    id: int
    field: str
    old_value: str | None
    new_value: str | None
    actor: UserResponse
    created_at: datetime.datetime
