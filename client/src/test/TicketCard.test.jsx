import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TicketCard from '../components/TicketCard'

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
    due_date: new Date(Date.now() + 3600_000).toISOString(),
    resolved_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('TicketCard', () => {
  it('renders title, badges, and meta', () => {
    render(
      <ul>
        <TicketCard ticket={makeTicket()} onSelect={() => {}} />
      </ul>,
    )
    expect(screen.getByText('#7 Printer jams on duplex jobs')).toBeInTheDocument()
    expect(screen.getByText('P2 — High')).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('Printer')).toBeInTheDocument()
    expect(screen.getByText(/owner@example.com/)).toBeInTheDocument()
    expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
  })

  it('shows an overdue badge for unresolved tickets past their due date', () => {
    const pastDue = makeTicket({ due_date: new Date(Date.now() - 3600_000).toISOString() })
    render(
      <ul>
        <TicketCard ticket={pastDue} onSelect={() => {}} />
      </ul>,
    )
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })

  it('does not mark resolved tickets overdue', () => {
    const resolved = makeTicket({
      status: 'resolved',
      due_date: new Date(Date.now() - 3600_000).toISOString(),
    })
    render(
      <ul>
        <TicketCard ticket={resolved} onSelect={() => {}} />
      </ul>,
    )
    expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
  })

  it('reports its ticket id when clicked', () => {
    const onSelect = vi.fn()
    render(
      <ul>
        <TicketCard ticket={makeTicket()} onSelect={onSelect} />
      </ul>,
    )
    screen.getByRole('button').click()
    expect(onSelect).toHaveBeenCalledWith(7)
  })
})
