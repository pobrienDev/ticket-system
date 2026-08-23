import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from '../components/Dashboard'

vi.mock('../api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    listTickets: vi.fn(),
    getStats: vi.fn(),
    listCategories: vi.fn(),
    listUsers: vi.fn(),
    createTicket: vi.fn(),
  },
}))

import { api } from '../api'

const admin = { id: 1, email: 'admin@example.com', is_admin: true }

function makeTicket(id, overrides = {}) {
  return {
    id,
    title: `Ticket ${id}`,
    description: '',
    status: 'new',
    priority: 3,
    owner: { id: 2, email: 'owner@example.com' },
    assignee: null,
    category: null,
    due_date: new Date(Date.now() + 3600_000).toISOString(),
    resolved_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

const stats = {
  total: 30,
  by_status: { new: 4, open: 10, in_progress: 6, resolved: 7, closed: 3 },
  unresolved: 20,
  p1_unresolved: 2,
  unassigned_unresolved: 9,
  overdue: 5,
  avg_resolution_hours: 27.1,
}

beforeEach(() => {
  vi.clearAllMocks()
  window.location.hash = ''
  api.getStats.mockResolvedValue(stats)
  api.listCategories.mockResolvedValue([])
  api.listUsers.mockResolvedValue([])
  api.listTickets.mockResolvedValue({
    items: [makeTicket(1), makeTicket(2)],
    total: 30,
    limit: 20,
    offset: 0,
  })
})

describe('Dashboard', () => {
  it('renders stats tiles, tickets, and pagination footer', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)

    expect(await screen.findByText('#1 Ticket 1')).toBeInTheDocument()
    expect(screen.getByText('Unresolved')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument() // unresolved value
    expect(screen.getByText('Overdue')).toBeInTheDocument()
    expect(screen.getByText('30 tickets')).toBeInTheDocument()
    expect(screen.getByText('Showing 2 of 30')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load more' })).toBeInTheDocument()
  })

  it('scopes the query to the signed-in user via the chips', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    screen.getByRole('button', { name: 'Assigned to me' }).click()
    await vi.waitFor(() => {
      const lastCall = api.listTickets.mock.calls.at(-1)[0]
      expect(lastCall.assignee_id).toBe(admin.id)
      expect(lastCall.scope).toBeUndefined() // scope is translated, not sent
    })
  })

  it('opens a ticket through the URL hash', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    screen.getByText('#1 Ticket 1').closest('button').click()
    expect(window.location.hash).toBe('#ticket-1')
  })
})
