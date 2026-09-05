"""Ticket comments. Nested under /tickets/{ticket_id}/comments.

Comments are read as part of the ticket detail response, so this router only
needs a create endpoint.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_current_user, get_db
from .tickets import get_visible_ticket_or_404

router = APIRouter(prefix="/tickets/{ticket_id}/comments", tags=["comments"])


@router.post("", response_model=schemas.CommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    ticket_id: int,
    comment: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Same visibility rule as reading: you can only comment on tickets you can see.
    ticket = get_visible_ticket_or_404(ticket_id, db, current_user)
    new_comment = models.Comment(
        ticket_id=ticket.id,
        body=comment.body,
        author_id=current_user.id,  # from the token, same principle as ticket ownership
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment
