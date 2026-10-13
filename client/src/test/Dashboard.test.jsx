// The main authenticated screen, rendered with its real child components
// and the network layer mocked at the module boundary. These are the
// integration tests of the frontend: stats, queue loading, pagination, the
// stale-response guard, error states, ticket creation, role-dependent data,
// and hash-based navigation between the list and a ticket.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { deferred } from './helpers'
import Dashboard from '../components/Dashboard'

vi.mock('../api', () => ({
  ApiError: class ApiError extends Error {
    constructor(message, status) {
      super(message)
      this.status = status
    }
  },
  api: {
    listTickets: vi.fn(),
    getStats: vi.fn(),
    listCategories: vi.fn(),
    listUsers: vi.fn(),
    createTicket: vi.fn(),
    getTicket: vi.fn(),
    updateTicket: vi.fn(),
    deleteTicket: vi.fn(),
    addComment: vi.fn(),
    getAuditLog: vi.fn(),
  },
}))

import { ApiError, api } from '../api'

const admin = { id: 1, email: 'admin@example.com', is_admin: true }
const requester = { id: 4, email: 'priya@example.com', is_admin: false }

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

function page(items, total, offset = 0) {
  return { items, total, limit: 20, offset }
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
  api.listCategories.mockResolvedValue([{ id: 1, name: 'Printer' }])
  api.listUsers.mockResolvedValue([{ id: 3, email: 'agent@example.com' }])
  api.listTickets.mockResolvedValue(page([makeTicket(1), makeTicket(2)], 30))
  api.getTicket.mockImplementation(async (id) => ({ ...makeTicket(id), comments: [] }))
})

// --- Initial load -----------------------------------------------------------

describe('initial load', () => {
  it('renders stats tiles, tickets, and the pagination footer', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)

    expect(await screen.findByText('#1 Ticket 1')).toBeInTheDocument()
    expect(screen.getByText('Unresolved')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument() // unresolved value
    expect(screen.getByText('Overdue')).toBeInTheDocument()
    expect(screen.getByText('30 tickets')).toBeInTheDocument()
    expect(screen.getByText('Showing 2 of 30')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load more' })).toBeInTheDocument()
  })

  it('requests the first page with the default sort and no scope', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    const query = api.listTickets.mock.calls[0][0]
    expect(query).toMatchObject({ limit: 20, offset: 0, sort: '-created_at' })
    expect(query.scope).toBeUndefined()
    expect(api.getStats).toHaveBeenCalled()
  })

  it('shows the empty state and no footer when nothing matches', async () => {
    api.listTickets.mockResolvedValue(page([], 0))
    render(<Dashboard user={admin} onLogout={() => {}} />)

    expect(await screen.findByText('No tickets match the current filters.')).toBeInTheDocument()
    expect(screen.getByText('0 tickets')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })
})

// --- Stats tiles ------------------------------------------------------------

describe('stats tiles', () => {
  it('formats resolution time in hours below two days and days above', async () => {
    api.createTicket.mockResolvedValue(makeTicket(50))
    render(<Dashboard user={admin} onLogout={() => {}} />)
    expect(await screen.findByText('27h')).toBeInTheDocument()

    // Stats refresh after a mutation (creating a ticket), not on filter changes.
    api.getStats.mockResolvedValue({ ...stats, avg_resolution_hours: 60 })
    await userEvent.type(screen.getByLabelText('Title'), 'Anything')
    await userEvent.click(screen.getByRole('button', { name: 'Create ticket' }))
    expect(await screen.findByText('2.5d')).toBeInTheDocument()
  })

  it('loads stats once, not again on every filter change', async () => {
    // Stats cover everything the user can see regardless of filters, so a
    // filter change (every debounced search keystroke) must not refetch them.
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    expect(api.getStats).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'open' } })
    await waitFor(() => expect(api.listTickets).toHaveBeenCalledTimes(2))
    expect(api.getStats).toHaveBeenCalledTimes(1)
  })

  it('shows a dash when nothing has been resolved yet', async () => {
    api.getStats.mockResolvedValue({ ...stats, avg_resolution_hours: null })
    render(<Dashboard user={admin} onLogout={() => {}} />)
    expect(await screen.findByText('—')).toBeInTheDocument()
  })

  it('highlights P1 and overdue tiles only when their count is non-zero', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    // The value elements: P1 urgent = 2 and Overdue = 5 (both alerting),
    // Unassigned = 9 (never alerts).
    expect(screen.getByText('P1 urgent').closest('.stat')).toHaveClass('stat--alert')
    expect(screen.getByText('Overdue').closest('.stat')).toHaveClass('stat--alert')
    expect(screen.getByText('Unassigned').closest('.stat')).not.toHaveClass('stat--alert')
  })

  it('does not highlight an alerting tile whose count is zero', async () => {
    api.getStats.mockResolvedValue({ ...stats, p1_unresolved: 0, overdue: 0 })
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    expect(screen.getByText('P1 urgent').closest('.stat')).not.toHaveClass('stat--alert')
    expect(screen.getByText('Overdue').closest('.stat')).not.toHaveClass('stat--alert')
  })
})

// --- Pagination -------------------------------------------------------------

describe('pagination', () => {
  it('appends the next page on Load more and hides the footer when complete', async () => {
    // A full first page of 20; the next request starts where it ended.
    const firstPage = Array.from({ length: 20 }, (_, i) => makeTicket(i + 1))
    api.listTickets.mockResolvedValueOnce(page(firstPage, 22))
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    // Second page: two more tickets, and now the total says that's everything.
    api.listTickets.mockResolvedValue(page([makeTicket(21), makeTicket(22)], 22, 20))
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('#22 Ticket 22')).toBeInTheDocument()
    expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20 }))
    // Earlier items are kept (append), not replaced.
    expect(screen.getByText('#1 Ticket 1')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(22)
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('shows progress and disables Load more while the next page is in flight', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    const pending = deferred()
    api.listTickets.mockReturnValueOnce(pending.promise)

    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()

    pending.resolve(page([makeTicket(3)], 30, 20))
    expect(await screen.findByText('#3 Ticket 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load more' })).toBeEnabled()
  })

  it('ignores Load more while a filter change is still loading its first page', async () => {
    // Otherwise page 2 of the NEW filters would be appended to page 1 of the
    // OLD ones, and the sequence guard would then discard the new page 1 as
    // "older" — a list mixing two queries.
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    const reset = deferred()
    api.listTickets.mockReturnValueOnce(reset.promise)
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'open' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(api.listTickets).toHaveBeenCalledTimes(2) // the reset only; the click was ignored

    reset.resolve(page([makeTicket(9)], 30))
    expect(await screen.findByText('#9 Ticket 9')).toBeInTheDocument()
    expect(screen.queryByText('#1 Ticket 1')).not.toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
  })

  it('resets to the first page when a filter changes', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    api.listTickets.mockResolvedValue(page([makeTicket(3)], 30, 20))
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    await screen.findByText('#3 Ticket 3')

    api.listTickets.mockResolvedValue(page([makeTicket(9)], 1))
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'open' } })

    expect(await screen.findByText('#9 Ticket 9')).toBeInTheDocument()
    expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'open', offset: 0 }))
    // Replaced, not appended: the previous pages are gone.
    expect(screen.queryByText('#1 Ticket 1')).not.toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
  })
})

// --- Stale responses --------------------------------------------------------

describe('stale-response guard', () => {
  it('ignores a slow earlier response that arrives after a newer one', async () => {
    // Two filter changes in quick succession produce two in-flight requests.
    // If the FIRST resolves LAST, its (stale) result must be discarded — the
    // request sequence counter in loadTickets is what makes this hold.
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    const first = deferred()
    const second = deferred()
    api.listTickets.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'open' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'closed' } })

    second.resolve(page([makeTicket(9, { title: 'Newer result' })], 1))
    expect(await screen.findByText('#9 Newer result')).toBeInTheDocument()

    first.resolve(page([makeTicket(8, { title: 'Stale result' })], 1))
    // Give the stale promise every chance to apply, then confirm it didn't.
    await waitFor(() => expect(api.listTickets).toHaveBeenCalledTimes(3))
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByText('#8 Stale result')).not.toBeInTheDocument()
    expect(screen.getByText('#9 Newer result')).toBeInTheDocument()
  })
})

// --- Errors -----------------------------------------------------------------

describe('errors', () => {
  it('shows the error message in a banner and drops the loading state', async () => {
    // The network layer shapes every failure (HTTP error, timeout, refused
    // connection) into one message, so the banner just shows it.
    api.listTickets.mockRejectedValue(new ApiError('Something went wrong', 500))
    render(<Dashboard user={admin} onLogout={() => {}} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
    expect(screen.queryByText('Loading tickets…')).not.toBeInTheDocument()
  })
})

// --- Creating a ticket ------------------------------------------------------

describe('creating a ticket', () => {
  it('submits normalized values and refreshes the queue and stats', async () => {
    api.createTicket.mockResolvedValue(makeTicket(50))
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    const listCallsBefore = api.listTickets.mock.calls.length
    const statsCallsBefore = api.getStats.mock.calls.length

    await userEvent.type(screen.getByLabelText('Title'), 'Dead monitor')
    await userEvent.selectOptions(screen.getByLabelText('Priority'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Create ticket' }))

    // The form holds strings; the API receives a number and an explicit null.
    expect(api.createTicket).toHaveBeenCalledWith({
      title: 'Dead monitor',
      description: '',
      priority: 1,
      category_id: null,
    })
    await waitFor(() => {
      expect(api.listTickets.mock.calls.length).toBe(listCallsBefore + 1)
      expect(api.getStats.mock.calls.length).toBe(statsCallsBefore + 1)
    })
  })
})

// --- Roles and session ------------------------------------------------------

describe('roles', () => {
  it('loads the user list only for admins', async () => {
    const { unmount } = render(<Dashboard user={requester} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    // Regular users can't call /users (403), so it's never requested.
    expect(api.listUsers).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Assignee')).not.toBeInTheDocument()
    unmount()

    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')
    expect(api.listUsers).toHaveBeenCalledOnce()
    expect(screen.getByLabelText('Assignee')).toBeInTheDocument()
  })

  it('shows the admin badge and signs out via the header', async () => {
    const onLogout = vi.fn()
    render(<Dashboard user={admin} onLogout={onLogout} />)
    await screen.findByText('#1 Ticket 1')

    expect(screen.getByText('admin')).toHaveClass('badge--admin')
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(onLogout).toHaveBeenCalledOnce()
  })
})

// --- Scope and navigation ---------------------------------------------------

describe('scope and navigation', () => {
  it('scopes the query to the signed-in user via the chips', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    fireEvent.click(screen.getByRole('button', { name: 'Assigned to me' }))
    await waitFor(() => {
      const lastCall = api.listTickets.mock.calls.at(-1)[0]
      expect(lastCall.assignee_id).toBe(admin.id)
      expect(lastCall.scope).toBeUndefined() // scope is translated, not sent
    })

    fireEvent.click(screen.getByRole('button', { name: 'Opened by me' }))
    await waitFor(() => {
      const lastCall = api.listTickets.mock.calls.at(-1)[0]
      expect(lastCall.owner_id).toBe(admin.id)
      // The assignee pin from the previous scope is gone; what remains is the
      // dropdown's default (''), which api.js drops before the request.
      expect(lastCall.assignee_id).not.toBe(admin.id)
    })
  })

  it('opens a ticket through the URL hash', async () => {
    render(<Dashboard user={admin} onLogout={() => {}} />)
    await screen.findByText('#1 Ticket 1')

    // The card is a link to the ticket's hash; the browser following it is
    // what opens the ticket. jsdom does not navigate on anchor clicks, so the
    // test sets the hash the link points at and checks the Dashboard reacts.
    expect(screen.getByText('#1 Ticket 1').closest('a')).toHaveAttribute('href', '#ticket-1')
    window.location.hash = '#ticket-1'
    // The detail view loads the ticket by id.
    expect(await screen.findByRole('heading', { level: 2, name: '#1 Ticket 1' })).toBeInTheDocument()
    expect(api.getTicket).toHaveBeenCalledWith(1)
  })

  it('restores an open ticket from the hash on load, and returns to the list', async () => {
    // A refresh (or a shared link) with #ticket-5 lands on that ticket, not
    // the list; Back clears the hash and the list re-renders.
    window.location.hash = '#ticket-5'
    render(<Dashboard user={admin} onLogout={() => {}} />)

    expect(await screen.findByRole('heading', { level: 2, name: '#5 Ticket 5' })).toBeInTheDocument()
    expect(api.getTicket).toHaveBeenCalledWith(5)

    fireEvent.click(screen.getByRole('button', { name: '← Back to tickets' }))
    expect(await screen.findByText('#1 Ticket 1')).toBeInTheDocument()
    expect(window.location.hash).toBe('')
  })
})
