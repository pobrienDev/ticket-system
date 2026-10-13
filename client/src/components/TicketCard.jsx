// One row in the queue. The whole card is a single link to the ticket's
// hash: keyboard-focusable, announced as one item by screen readers, and a
// real URL (copyable, middle-clickable) — the hash is how the Dashboard
// decides which ticket is open, so no click handler is needed.
import { formatDate } from '../constants'
import TicketBadges from './TicketBadges'

function TicketCard({ ticket }) {
  return (
    <li className={`ticket-card ticket-card--${ticket.status}`}>
      <a className="ticket-card__link" href={`#ticket-${ticket.id}`}>
        <div className="ticket-card__title-row">
          <TicketBadges ticket={ticket} />
          <h3>
            #{ticket.id} {ticket.title}
          </h3>
        </div>
        {ticket.description && <p className="ticket-card__description">{ticket.description}</p>}
        <p className="ticket-card__meta">
          Opened by {ticket.owner.email} ·{' '}
          {ticket.assignee ? `assigned to ${ticket.assignee.email}` : 'unassigned'} · updated{' '}
          {formatDate(ticket.updated_at)}
        </p>
      </a>
    </li>
  )
}

export default TicketCard
