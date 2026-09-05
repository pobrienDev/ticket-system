"""Shared FastAPI dependencies: database session and the auth gates.

Handlers declare what they need (`Depends(get_db)`, `Depends(get_current_user)`)
and FastAPI resolves it per request. Tests swap get_db for a test-engine
version through app.dependency_overrides, so the real handlers run unchanged.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .auth import decode_access_token
from .database import SessionLocal

# Reads the bearer token from the Authorization header; tokenUrl only tells
# the OpenAPI docs where to obtain one.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    # Yield-style dependency: the session lives for the request and is closed
    # after the response is sent, whether the handler succeeded or raised.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    """Resolve the bearer token to a User row, or 401.

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
    if payload is None or payload.get("sub") is None:
        raise credentials_error
    user = db.query(models.User).filter(models.User.id == int(payload["sub"])).first()
    if user is None:
        raise credentials_error
    return user


def get_current_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    # 401 means "we don't know who you are"; 403 means "we do, and no".
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
