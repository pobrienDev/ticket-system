import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..dependencies import get_current_admin, get_current_user, get_db
from ..models import utcnow
from ..notifications import notify_assignment

router = APIRouter(prefix="/tickets", tags=["tickets"])

SORT_OPTIONS = {
    "priority": models.Ticket.priority.asc(),  # 1 = highest, so ascending puts urgent first
    "-priority": models.Ticket.priority.desc(),
    "created_at": models.Ticket.created_at.asc(),
    "-created_at": models.Ticket.created_at.desc(),
    "due_date": models.Ticket.due_date.asc(),
}

# Unresolved = still needs work. Used by scoping-free helpers below and stats.
UNRESOLVED_STATUSES = (models.TicketStatus.new, models.TicketStatus.open, models.TicketStatus.in_progress)


def visible_tickets(db: Session, user: models.User):
    """Tickets this user may see: admins see all, everyone else their own or assigned."""
    query = db.query(models.Ticket)
    if not user.is_admin:
        query = query.filter(
            or_(models.Ticket.owner_id == user.id, models.Ticket.assignee_id == user.id)
        )
    return query


def get_visible_ticket_or_404(ticket_id: int, db: Session, user: models.User) -> models.Ticket:
    # 404 (not 403) for tickets outside the user's scope, so IDs can't be probed.
    ticket = visible_tickets(db, user).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def record_change(db: Session, ticket: models.Ticket, actor: models.User, field: str, old, new):
    def clip(value):
        if value is None:
            return None
        text = str(value)
        return text if len(text) <= 120 else text[:117] + "..."

    db.add(
        models.AuditLogEntry(
            ticket_id=ticket.id,
            actor_id=actor.id,
            field=field,
            old_value=clip(old),
            new_value=clip(new),
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
    now = utcnow()  # one timestamp so due_date is exactly created_at + SLA
    new_ticket = models.Ticket(
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        category_id=ticket.category_id,
        owner_id=current_user.id,  # from the token, not from the client
        created_at=now,
        updated_at=now,
        due_date=now + datetime.timedelta(hours=models.SLA_HOURS[ticket.priority]),
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
    owner_id: int | None = None,
    q: str | None = None,
    sort: str = Query(default="-created_at", pattern="^(-?(priority|created_at)|due_date)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = visible_tickets(db, user)
    if status_filter is not None:
        query = query.filter(models.Ticket.status == status_filter)
    if category_id is not None:
        query = query.filter(models.Ticket.category_id == category_id)
    if assignee_id is not None:
        query = query.filter(models.Ticket.assignee_id == assignee_id)
    if owner_id is not None:
        query = query.filter(models.Ticket.owner_id == owner_id)
    if q:
        needle = f"%{q}%"
        query = query.filter(
            or_(models.Ticket.title.ilike(needle), models.Ticket.description.ilike(needle))
        )
    total = query.count()
    items = (
        query.options(
            joinedload(models.Ticket.owner),
            joinedload(models.Ticket.assignee),
            joinedload(models.Ticket.category),
        )
        # Secondary key keeps pagination stable when the sort column ties.
        .order_by(SORT_OPTIONS[sort], models.Ticket.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return schemas.TicketListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=schemas.TicketStatsResponse)
def ticket_stats(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Queue health for the tickets this user can see."""
    scope = visible_tickets(db, user)

    by_status = {s.value: 0 for s in models.TicketStatus}
    for status_value, count in (
        scope.with_entities(models.Ticket.status, func.count(models.Ticket.id))
        .group_by(models.Ticket.status)
        .all()
    ):
        by_status[status_value.value] = count

    unresolved = scope.filter(models.Ticket.status.in_(UNRESOLVED_STATUSES))
    p1_unresolved = unresolved.filter(models.Ticket.priority == 1).count()
    unassigned_unresolved = unresolved.filter(models.Ticket.assignee_id.is_(None)).count()
    overdue = unresolved.filter(models.Ticket.due_date < utcnow()).count()

    # Averaged in Python: resolved_at - created_at has no portable SQL form
    # across SQLite and Postgres, and resolved counts stay small.
    resolution_pairs = (
        scope.filter(models.Ticket.resolved_at.isnot(None))
        .with_entities(models.Ticket.created_at, models.Ticket.resolved_at)
        .all()
    )
    avg_resolution_hours = None
    if resolution_pairs:
        total_hours = sum((res - created).total_seconds() / 3600 for created, res in resolution_pairs)
        avg_resolution_hours = round(total_hours / len(resolution_pairs), 1)

    return schemas.TicketStatsResponse(
        total=scope.count(),
        by_status=by_status,
        unresolved=unresolved.count(),
        p1_unresolved=p1_unresolved,
        unassigned_unresolved=unassigned_unresolved,
        overdue=overdue,
        avg_resolution_hours=avg_resolution_hours,
    )


@router.get("/{ticket_id}", response_model=schemas.TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ticket = (
        visible_tickets(db, user)
        .options(
            joinedload(models.Ticket.owner),
            joinedload(models.Ticket.assignee),
            joinedload(models.Ticket.category),
            joinedload(models.Ticket.comments).joinedload(models.Comment.author),
        )
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = get_visible_ticket_or_404(ticket_id, db, current_user)
    changes = update.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    can_edit = current_user.is_admin or current_user.id in (ticket.owner_id, ticket.assignee_id)
    if not can_edit:
        raise HTTPException(
            status_code=403, detail="Only the ticket owner, assignee, or an admin can edit a ticket"
        )
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
        new_status = changes["status"]
        if new_status not in models.ALLOWED_TRANSITIONS[ticket.status]:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot move a ticket from {ticket.status.value} to {new_status.value}",
            )
        record_change(db, ticket, current_user, "status", ticket.status.value, new_status.value)
        if new_status == models.TicketStatus.resolved:
            ticket.resolved_at = utcnow()
        elif ticket.status in (models.TicketStatus.resolved, models.TicketStatus.closed):
            ticket.resolved_at = None  # reopened

    # Audit the remaining editable fields too — history should not be
    # limited to status and assignment.
    if "priority" in changes and changes["priority"] != ticket.priority:
        record_change(db, ticket, current_user, "priority", f"P{ticket.priority}", f"P{changes['priority']}")
    if "title" in changes and changes["title"] != ticket.title:
        record_change(db, ticket, current_user, "title", ticket.title, changes["title"])
    if "description" in changes and changes["description"] != ticket.description:
        record_change(db, ticket, current_user, "description", ticket.description, changes["description"])
    if "category_id" in changes and changes["category_id"] != ticket.category_id:
        old_name = ticket.category.name if ticket.category else None
        new_name = None
        if changes["category_id"] is not None:
            new_name = db.query(models.Category.name).filter(
                models.Category.id == changes["category_id"]
            ).scalar()
        record_change(db, ticket, current_user, "category", old_name, new_name)

    assignee_changed = "assignee_id" in changes and changes["assignee_id"] != ticket.assignee_id

    for field, value in changes.items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)

    # Notify after the assignment is safely committed, and off the request
    # path — a slow or failed email (logged inside notify_assignment) must
    # never stall or break the PATCH response.
    if assignee_changed and new_assignee is not None:
        background_tasks.add_task(notify_assignment, ticket, new_assignee.email)

    return ticket


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    ticket = get_visible_ticket_or_404(ticket_id, db, admin)
    db.delete(ticket)
    db.commit()


@router.get("/{ticket_id}/audit", response_model=list[schemas.AuditLogResponse])
def get_audit_log(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ticket = get_visible_ticket_or_404(ticket_id, db, user)
    return (
        db.query(models.AuditLogEntry)
        .options(joinedload(models.AuditLogEntry.actor))
        .filter(models.AuditLogEntry.ticket_id == ticket.id)
        .order_by(models.AuditLogEntry.created_at)
        .all()
    )
