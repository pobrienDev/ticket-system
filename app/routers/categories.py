from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_current_admin, get_current_user, get_db

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[schemas.CategoryResponse])
def list_categories(
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    return db.query(models.Category).order_by(models.Category.name).all()


@router.post("", response_model=schemas.CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    duplicate = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")
    if db.query(models.Category).filter(models.Category.name == category.name).first():
        raise duplicate
    new_category = models.Category(name=category.name)
    db.add(new_category)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent create slipped past the check; the unique constraint wins.
        db.rollback()
        raise duplicate from None
    db.refresh(new_category)
    return new_category
