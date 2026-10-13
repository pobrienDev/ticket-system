// The priority / status / overdue / category badge row. Rendered identically
// on the queue card and the detail view, so it lives in one place.
import { isOverdue, priorityLabel, statusLabel } from '../constants'

function TicketBadges({ ticket }) {
  return (
    <>
      <span className={`badge badge--p${ticket.priority}`}>{priorityLabel(ticket.priority)}</span>
      <span className={`badge badge--status badge--status-${ticket.status}`}>{statusLabel(ticket.status)}</span>
      {isOverdue(ticket) && <span className="badge badge--overdue">Overdue</span>}
      {ticket.category && <span className="badge badge--category">{ticket.category.name}</span>}
    </>
  )
}

export default TicketBadges
