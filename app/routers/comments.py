from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_current_user, get_db

router = APIRouter(prefix="/tickets/{ticket_id}/comments", tags=["comments"])


@router.post("", response_model=schemas.CommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    ticket_id: int,
    comment: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    new_comment = models.Comment(
        ticket_id=ticket.id,
        body=comment.body,
        author_id=current_user.id,  # from the token, same principle as ticket ownership
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment
