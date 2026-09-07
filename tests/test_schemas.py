"""Validation rules in app/schemas.py, exercised directly.

The API tests prove these through HTTP (422s); these pin the rules at the
schema level, where the intent is easiest to read: trimming, the
null-vs-omitted distinction, positive ids, and unknown fields being
dropped rather than applied.
"""

import pytest
from pydantic import ValidationError

from app import models, schemas

# --- NonBlank ---------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\n\t "])
def test_non_blank_rejects_empty_and_whitespace(raw):
    with pytest.raises(ValidationError, match="must not be blank"):
        schemas.TicketCreate(title=raw)


def test_non_blank_trims_but_keeps_inner_whitespace():
    assert schemas.TicketCreate(title="  Printer  jams  ").title == "Printer  jams"
    assert schemas.CommentCreate(body="\tnote\n").body == "note"
    assert schemas.CategoryCreate(name=" Network ").name == "Network"


def test_length_caps_apply_before_trimming():
    # The cap is on what the client sent; padding does not buy extra room.
    with pytest.raises(ValidationError):
        schemas.TicketCreate(title="x" * schemas.TITLE_MAX + " ")
    assert schemas.TicketCreate(title="x" * schemas.TITLE_MAX).title == "x" * schemas.TITLE_MAX


# --- Priority and ids -------------------------------------------------------


def test_priority_bounds_come_from_the_model():
    # One source of truth: the schema range equals the database CHECK range.
    assert schemas.TicketCreate(title="t", priority=models.PRIORITY_MIN).priority == models.PRIORITY_MIN
    assert schemas.TicketCreate(title="t", priority=models.PRIORITY_MAX).priority == models.PRIORITY_MAX
    for bad in (models.PRIORITY_MIN - 1, models.PRIORITY_MAX + 1):
        with pytest.raises(ValidationError):
            schemas.TicketCreate(title="t", priority=bad)


@pytest.mark.parametrize("bad_id", [0, -1])
def test_reference_ids_must_be_positive(bad_id):
    # 0 or a negative id can never match a row: invalid input, not "unknown".
    with pytest.raises(ValidationError):
        schemas.TicketCreate(title="t", category_id=bad_id)
    with pytest.raises(ValidationError):
        schemas.TicketUpdate(assignee_id=bad_id)


# --- Partial updates: omitted vs null --------------------------------------


def test_update_distinguishes_omitted_from_null():
    # Omitted fields are absent from the dump the router applies...
    assert schemas.TicketUpdate(priority=1).model_dump(exclude_unset=True) == {"priority": 1}
    # ...a nullable reference may be explicitly nulled (unassign / clear)...
    assert schemas.TicketUpdate(assignee_id=None).model_dump(exclude_unset=True) == {"assignee_id": None}
    assert schemas.TicketUpdate(category_id=None).model_dump(exclude_unset=True) == {"category_id": None}
    # ...but NOT NULL columns reject an explicit null outright.
    for field in ("title", "description", "status", "priority"):
        with pytest.raises(ValidationError, match=f"{field} cannot be null"):
            schemas.TicketUpdate(**{field: None})


# --- Mass assignment --------------------------------------------------------


def test_unknown_fields_are_dropped_not_applied():
    # Ownership and roles never come from the body; a client naming them is
    # ignored rather than rejected (see the module docstring for the trade-off).
    ticket = schemas.TicketCreate.model_validate({"title": "t", "owner_id": 42, "status": "closed"})
    assert not hasattr(ticket, "owner_id")
    assert not hasattr(ticket, "status")
    user = schemas.UserCreate.model_validate(
        {"email": "a@example.com", "password": "longenough123", "is_admin": True}
    )
    assert not hasattr(user, "is_admin")


# --- Passwords --------------------------------------------------------------


def test_password_limit_is_measured_in_bytes():
    ascii_max = "x" * schemas.BCRYPT_MAX_PASSWORD_BYTES
    assert schemas.UserCreate(email="a@example.com", password=ascii_max).password == ascii_max
    with pytest.raises(ValidationError, match="bytes"):
        schemas.UserCreate(email="a@example.com", password="é" * schemas.BCRYPT_MAX_PASSWORD_BYTES)
