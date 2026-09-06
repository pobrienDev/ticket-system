// One row in the queue. Purely presentational, so the tests check what a
// ticket's fields turn into on screen: badges, optional parts, the meta
// line, the styling hooks the stylesheet relies on, and that the card is a
// single accessible button.
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TicketCard from '../components/TicketCard'

const HOUR = 3600_000

function makeTicket(overrides = {}) {
  return {
    id: 7,
    title: 'Printer jams on duplex jobs',
    description: 'Tray 2 keeps jamming.',
    status: 'open',
    priority: 2,
    owner: { id: 1, email: 'owner@example.com' },
    assignee: null,
    category: { id: 1, name: 'Printer' },
    due_date: new Date(Date.now() + HOUR).toISOString(),
    resolved_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

// TicketCard renders an <li>, so it needs a list parent to be valid HTML.
function renderCard(ticket, onSelect = () => {}) {
  return render(
    <ul>
      <TicketCard ticket={ticket} onSelect={onSelect} />
    </ul>,
  )
}

// --- Content ----------------------------------------------------------------

describe('content', () => {
  it('renders title, badges, description, and meta', () => {
    renderCard(makeTicket())
    expect(screen.getByText('#7 Printer jams on duplex jobs')).toBeInTheDocument()
    expect(screen.getByText('P2 — High')).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('Printer')).toBeInTheDocument()
    expect(screen.getByText('Tray 2 keeps jamming.')).toBeInTheDocument()
    expect(screen.getByText(/Opened by owner@example.com/)).toBeInTheDocument()
    expect(screen.getByText(/updated/)).toBeInTheDocument()
    expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
  })

  it('shows the assignee when there is one, and "unassigned" otherwise', () => {
    // Assignment is the most-scanned fact in a queue; both states are explicit.
    const { unmount } = renderCard(makeTicket())
    expect(screen.getByText(/unassigned/)).toBeInTheDocument()
    unmount()

    renderCard(makeTicket({ assignee: { id: 2, email: 'agent@example.com' } }))
    expect(screen.getByText(/assigned to agent@example.com/)).toBeInTheDocument()
    expect(screen.queryByText(/unassigned/)).not.toBeInTheDocument()
  })

  it('omits the category badge and description when they are empty', () => {
    // Optional parts render nothing rather than an empty badge or a blank
    // paragraph, so uncategorized or terse tickets stay compact.
    renderCard(makeTicket({ category: null, description: '' }))
    expect(screen.queryByText('Printer')).not.toBeInTheDocument()
    expect(document.querySelector('.ticket-card__description')).toBeNull()
  })
})

// --- Overdue ----------------------------------------------------------------

describe('overdue badge', () => {
  it('appears for unresolved tickets past their due date', () => {
    renderCard(makeTicket({ status: 'new', due_date: new Date(Date.now() - HOUR).toISOString() }))
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })

  it('never appears on resolved or closed tickets, however late', () => {
    for (const status of ['resolved', 'closed']) {
      const { unmount } = renderCard(
        makeTicket({ status, due_date: new Date(Date.now() - HOUR).toISOString() }),
      )
      expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
      unmount()
    }
  })
})

// --- Styling hooks ----------------------------------------------------------

describe('styling hooks', () => {
  it('exposes the status on the card and the badge for the stylesheet', () => {
    // App.css keys off these: ticket-card--new gets the amber edge,
    // resolved/closed cards are muted, and each status badge has its color.
    // They are part of the component's contract with the stylesheet.
    renderCard(makeTicket({ status: 'new' }))
    expect(screen.getByRole('listitem')).toHaveClass('ticket-card', 'ticket-card--new')
    expect(screen.getByText('New')).toHaveClass('badge', 'badge--status', 'badge--status-new')
    expect(screen.getByText('P2 — High')).toHaveClass('badge--p2')
  })
})

// --- Interaction and accessibility -----------------------------------------

describe('interaction', () => {
  it('is a single button whose name includes the title', () => {
    // The whole card is one <button>, so keyboard users tab to the ticket
    // once and screen readers announce it as one actionable item.
    renderCard(makeTicket())
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toHaveAccessibleName(/#7 Printer jams on duplex jobs/)
  })

  it('reports its ticket id when clicked', () => {
    const onSelect = vi.fn()
    renderCard(makeTicket(), onSelect)
    screen.getByRole('button').click()
    expect(onSelect).toHaveBeenCalledWith(7)
  })
})
