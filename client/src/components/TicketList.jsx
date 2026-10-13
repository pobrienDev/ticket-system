// Renders the current page of tickets, or an empty state when the filters
// match nothing. Each card links to its ticket; the list holds no state.
import TicketCard from './TicketCard'

function TicketList({ tickets }) {
  if (tickets.length === 0) {
    return <p className="empty">No tickets match the current filters.</p>
  }

  return (
    <ul className="ticket-list">
      {tickets.map((ticket) => (
        <TicketCard key={ticket.id} ticket={ticket} />
      ))}
    </ul>
  )
}

export default TicketList
