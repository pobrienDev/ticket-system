"""Shared FastAPI dependencies: database session and the auth gates.

Handlers declare what they need (`Depends(get_db)`, `Depends(get_current_user)`)
and FastAPI resolves it per request. Tests swap get_db for a test-engine
version through app.dependency_overrides, so the real handlers run unchanged.

The two auth dependencies answer the two questions every protected request
must answer, in order: who are you (get_current_user → 401 if unknown), and
may you do this (get_current_admin → 403 if not). Relationship-based rules —
owner, assignee, visibility — live in the ticket router because they depend
on the ticket being acted on, not just on the caller.
"""

from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .auth import decode_access_token
from .database import SessionLocal

# Reads the bearer token from the Authorization header (401 if absent);
# tokenUrl only tells the OpenAPI docs where a token can be obtained.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Iterator[Session]:
    """Provide one database Session for the duration of a request.

    A yield-style dependency: FastAPI runs the code before `yield` when the
    request starts and the `finally` after the response is sent, so the
    session is always closed — and an uncommitted transaction rolled back —
    whether the handler returned normally or raised.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    """Resolve the bearer token to a User row, or 401.

    Every failure — unverifiable or expired token, a subject that is not an
    id, an id that no longer exists — produces the same 401, so the response
    reveals nothing about which check failed.

    The user is re-read from the database on every request rather than
    trusted from the token alone, so deleting an account or removing admin
    rights takes effect immediately even though the JWT itself is stateless.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        # Only the secret holder could mint a token with a malformed subject,
        # but it must still be a clean 401, never a 500.
        raise credentials_error from None
    user = db.get(models.User, user_id)
    if user is None:
        raise credentials_error
    return user


def get_current_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Require an authenticated admin, or 403.

    Composes on get_current_user, so an unauthenticated caller still gets a
    401 from that layer first. 401 means "we don't know who you are";
    403 means "we do, and the answer is no".
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
