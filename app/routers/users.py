from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import create_access_token, hash_password, verify_password
from ..dependencies import get_current_admin, get_current_user, get_db
from ..rate_limit import LOGIN_RATE_LIMIT, REGISTER_RATE_LIMIT, limiter

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_RATE_LIMIT)
def register(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Emails are stored lowercased so Joyce@ and joyce@ are one account.
    email = user.email.lower()
    duplicate = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if db.query(models.User).filter(models.User.email == email).first():
        raise duplicate
    new_user = models.User(email=email, hashed_password=hash_password(user.password))
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent registration slipped past the check; the unique index wins.
        db.rollback()
        raise duplicate from None
    db.refresh(new_user)
    return new_user


@auth_router.post("/login", response_model=schemas.Token)
@limiter.limit(LOGIN_RATE_LIMIT)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == form_data.username.lower()).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": str(user.id)})
    return schemas.Token(access_token=token)


@users_router.get("/me", response_model=schemas.UserResponse)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@users_router.get("", response_model=list[schemas.UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    return db.query(models.User).order_by(models.User.email).all()
