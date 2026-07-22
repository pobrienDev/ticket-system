import { priorityLabel, statusLabel } from '../constants'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function TicketCard({ ticket, onSelect }) {
  return (
    <li className={`ticket-card ticket-card--${ticket.status}`}>
      <button className="ticket-card__button" type="button" onClick={() => onSelect(ticket.id)}>
        <div className="ticket-card__title-row">
          <span className={`badge badge--p${ticket.priority}`}>{priorityLabel(ticket.priority)}</span>
          <span className="badge badge--status">{statusLabel(ticket.status)}</span>
          {ticket.category && <span className="badge badge--category">{ticket.category.name}</span>}
          <h3>
            #{ticket.id} {ticket.title}
          </h3>
        </div>
        {ticket.description && <p className="ticket-card__description">{ticket.description}</p>}
        <p className="ticket-card__meta">
          Opened by {ticket.owner.email} ·{' '}
          {ticket.assignee ? `assigned to ${ticket.assignee.email}` : 'unassigned'} · updated{' '}
          {dateFormat.format(new Date(ticket.updated_at))}
        </p>
      </button>
    </li>
  )
}

export default TicketCard
