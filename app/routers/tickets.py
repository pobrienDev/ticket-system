from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..dependencies import get_current_admin, get_current_user, get_db
from ..notifications import notify_assignment

router = APIRouter(prefix="/tickets", tags=["tickets"])

SORT_OPTIONS = {
    "priority": models.Ticket.priority.asc(),  # 1 = highest, so ascending puts urgent first
    "-priority": models.Ticket.priority.desc(),
    "created_at": models.Ticket.created_at.asc(),
    "-created_at": models.Ticket.created_at.desc(),
}


def get_ticket_or_404(ticket_id: int, db: Session) -> models.Ticket:
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def record_change(db: Session, ticket: models.Ticket, actor: models.User, field: str, old, new):
    db.add(
        models.AuditLogEntry(
            ticket_id=ticket.id,
            actor_id=actor.id,
            field=field,
            old_value=None if old is None else str(old),
            new_value=None if new is None else str(new),
        )
    )


@router.post("", response_model=schemas.TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    ticket: schemas.TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if ticket.category_id is not None:
        category = db.query(models.Category).filter(models.Category.id == ticket.category_id).first()
        if not category:
            raise HTTPException(status_code=400, detail="Unknown category_id")
    new_ticket = models.Ticket(
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        category_id=ticket.category_id,
        owner_id=current_user.id,  # from the token, not from the client
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket


@router.get("", response_model=schemas.TicketListResponse)
def list_tickets(
    status_filter: models.TicketStatus | None = Query(default=None, alias="status"),
    category_id: int | None = None,
    assignee_id: int | None = None,
    q: str | None = None,
    sort: str = Query(default="-created_at", pattern="^-?(priority|created_at)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    query = db.query(models.Ticket)
    if status_filter is not None:
        query = query.filter(models.Ticket.status == status_filter)
    if category_id is not None:
        query = query.filter(models.Ticket.category_id == category_id)
    if assignee_id is not None:
        query = query.filter(models.Ticket.assignee_id == assignee_id)
    if q:
        needle = f"%{q}%"
        query = query.filter(
            or_(models.Ticket.title.ilike(needle), models.Ticket.description.ilike(needle))
        )
    total = query.count()
    items = query.order_by(SORT_OPTIONS[sort]).offset(offset).limit(limit).all()
    return schemas.TicketListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=schemas.TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    ticket = (
        db.query(models.Ticket)
        .options(joinedload(models.Ticket.comments).joinedload(models.Comment.author))
        .filter(models.Ticket.id == ticket_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=schemas.TicketResponse)
def update_ticket(
    ticket_id: int,
    update: schemas.TicketUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = get_ticket_or_404(ticket_id, db)
    changes = update.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    if ticket.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only the ticket owner or an admin can edit a ticket")
    if "assignee_id" in changes and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can assign tickets")

    if changes.get("category_id") is not None:
        category = db.query(models.Category).filter(models.Category.id == changes["category_id"]).first()
        if not category:
            raise HTTPException(status_code=400, detail="Unknown category_id")

    new_assignee = None
    if "assignee_id" in changes:
        if changes["assignee_id"] is not None:
            new_assignee = db.query(models.User).filter(models.User.id == changes["assignee_id"]).first()
            if not new_assignee:
                raise HTTPException(status_code=400, detail="Unknown assignee_id")
        old_assignee = ticket.assignee
        if changes["assignee_id"] != ticket.assignee_id:
            record_change(
                db,
                ticket,
                current_user,
                "assignee",
                old_assignee.email if old_assignee else None,
                new_assignee.email if new_assignee else None,
            )

    if "status" in changes and changes["status"] != ticket.status:
        record_change(db, ticket, current_user, "status", ticket.status.value, changes["status"].value)

    assignee_changed = "assignee_id" in changes and changes["assignee_id"] != ticket.assignee_id

    for field, value in changes.items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)

    # Notify after the assignment is safely committed; a failed email is
    # logged inside notify_assignment and never bubbles up.
    if assignee_changed and new_assignee is not None:
        notify_assignment(ticket, new_assignee.email)

    return ticket


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    ticket = get_ticket_or_404(ticket_id, db)
    db.delete(ticket)
    db.commit()


@router.get("/{ticket_id}/audit", response_model=list[schemas.AuditLogResponse])
def get_audit_log(
    ticket_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    ticket = get_ticket_or_404(ticket_id, db)
    return ticket.audit_log
