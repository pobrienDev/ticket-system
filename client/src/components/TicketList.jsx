// Renders the current page of tickets, or an empty state when the filters
// match nothing. Selection is reported upward; the list holds no state.
import TicketCard from './TicketCard'

function TicketList({ tickets, onSelect }) {
  if (tickets.length === 0) {
    return <p className="empty">No tickets match the current filters.</p>
  }

  return (
    <ul className="ticket-list">
      {tickets.map((ticket) => (
        <TicketCard key={ticket.id} ticket={ticket} onSelect={onSelect} />
      ))}
    </ul>
  )
}

export default TicketList
