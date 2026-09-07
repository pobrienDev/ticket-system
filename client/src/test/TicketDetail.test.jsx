// The single-ticket view: loading and error states, role-dependent
// controls, the transition-limited status select, the in-flight guard,
// inline editing, history, comments, and deletion. The network layer is
// mocked at the module boundary; everything else runs for real.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TicketDetail from '../components/TicketDetail'

vi.mock('../api', () => ({
  api: {
    getTicket: vi.fn(),
    updateTicket: vi.fn(),
    deleteTicket: vi.fn(),
    addComment: vi.fn(),
    getAuditLog: vi.fn(),
  },
}))

import { api } from '../api'

const HOUR = 3600_000

const owner = { id: 2, email: 'owner@example.com', is_admin: false }
const agent = { id: 3, email: 'agent@example.com', is_admin: false }
const stranger = { id: 9, email: 'stranger@example.com', is_admin: false }
const admin = { id: 1, email: 'admin@example.com', is_admin: true }

const users = [
  { id: 1, email: 'admin@example.com' },
  { id: 3, email: 'agent@example.com' },
]
const categories = [
  { id: 1, name: 'Printer' },
  { id: 2, name: 'Network' },
]

function makeTicket(overrides = {}) {
  return {
    id: 12,
    title: 'MFA prompt loop',
    description: 'Authenticator prompts endlessly.',
    status: 'open',
    priority: 2,
    owner: { id: owner.id, email: owner.email, is_admin: false },
    assignee: null,
    category: { id: 1, name: 'Printer' },
    due_date: new Date(Date.now() + HOUR).toISOString(),
    resolved_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    comments: [],
    ...overrides,
  }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}

const noop = () => {}

async function renderDetail({ user = owner, ticket = makeTicket(), ...props } = {}) {
  api.getTicket.mockResolvedValue(ticket)
  const callbacks = { onBack: vi.fn(), onChanged: vi.fn(), onDeleted: vi.fn() }
  render(
    <TicketDetail
      ticketId={ticket.id}
      user={user}
      users={users}
      categories={categories}
      {...callbacks}
      {...props}
    />,
  )
  await screen.findByRole('heading', { level: 2 })
  return callbacks
}

beforeEach(() => {
  vi.clearAllMocks()
  // updateTicket answers with the merged patch by default, like the real API.
  api.updateTicket.mockImplementation(async (_id, patch) => ({ ...makeTicket(), ...patch }))
  api.getAuditLog.mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
})

// --- Loading and errors -----------------------------------------------------

describe('loading', () => {
  it('shows a loading state, then the ticket', async () => {
    const pending = deferred()
    api.getTicket.mockReturnValue(pending.promise)
    render(<TicketDetail ticketId={12} user={owner} users={users} categories={categories} onBack={noop} onChanged={noop} onDeleted={noop} />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading ticket…')
    pending.resolve(makeTicket())
    expect(await screen.findByRole('heading', { level: 2, name: '#12 MFA prompt loop' })).toBeInTheDocument()
    expect(api.getTicket).toHaveBeenCalledWith(12)
  })

  it('shows the error in place of the ticket and still offers Back', async () => {
    // A 404 (out of scope) or a network failure lands here; the user can
    // always get back to the list.
    api.getTicket.mockRejectedValue(new Error('Ticket not found'))
    const onBack = vi.fn()
    render(<TicketDetail ticketId={12} user={owner} users={users} categories={categories} onBack={onBack} onChanged={noop} onDeleted={noop} />)

    expect(await screen.findByRole('status')).toHaveTextContent('Ticket not found')
    fireEvent.click(screen.getByRole('button', { name: '← Back to tickets' }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})

// --- Rendering --------------------------------------------------------------

describe('rendering', () => {
  it('shows badges, title, description, and the meta line', async () => {
    await renderDetail({ ticket: makeTicket({ assignee: { id: 3, email: 'agent@example.com' } }) })

    // Badge text also appears as <option> text in the controls, so the
    // queries are scoped to badges.
    expect(screen.getByText('P2 — High', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText('Open', { selector: '.badge' })).toHaveClass('badge--status-open')
    expect(screen.getByText('Printer', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText('Authenticator prompts endlessly.')).toBeInTheDocument()
    const meta = screen.getByText(/Opened by owner@example.com/)
    expect(meta).toHaveTextContent('assigned to agent@example.com')
    expect(meta).toHaveTextContent(/· due /)
    expect(meta).not.toHaveTextContent(/resolved/)
    expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
  })

  it('shows the overdue badge on an unresolved ticket past its due date', async () => {
    await renderDetail({ ticket: makeTicket({ due_date: new Date(Date.now() - HOUR).toISOString() }) })
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })

  it('shows the resolved timestamp and no overdue badge on a resolved ticket', async () => {
    await renderDetail({
      ticket: makeTicket({
        status: 'resolved',
        due_date: new Date(Date.now() - HOUR).toISOString(),
        resolved_at: new Date().toISOString(),
      }),
    })
    expect(screen.getByText(/Opened by/)).toHaveTextContent(/· resolved /)
    expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
  })

  it('lists comments with their authors, or an empty state', async () => {
    await renderDetail({
      ticket: makeTicket({
        comments: [
          { id: 1, body: 'Cleared the stale registration.', author: { id: 3, email: 'agent@example.com' }, created_at: new Date().toISOString() },
          { id: 2, body: 'Still looping.', author: { id: 2, email: 'owner@example.com' }, created_at: new Date().toISOString() },
        ],
      }),
    })
    expect(screen.getByRole('heading', { level: 3, name: 'Comments (2)' })).toBeInTheDocument()
    expect(screen.getByText('Cleared the stale registration.')).toBeInTheDocument()
    expect(screen.getByText(/agent@example.com ·/)).toBeInTheDocument()
    expect(screen.queryByText('No comments yet.')).not.toBeInTheDocument()
  })
})

// --- Role-dependent controls -----------------------------------------------

describe('controls by role', () => {
  it('owner: status, priority, and edit — no assignee control, no delete', async () => {
    await renderDetail({ user: owner })
    expect(screen.getByLabelText('Status')).toBeInTheDocument()
    expect(screen.getByLabelText('Priority')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit details' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Assignee')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('assignee: the same working controls as the owner', async () => {
    await renderDetail({ user: agent, ticket: makeTicket({ assignee: { id: 3, email: 'agent@example.com' } }) })
    expect(screen.getByLabelText('Status')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit details' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Assignee')).not.toBeInTheDocument()
  })

  it('unrelated user: read-only apart from history', async () => {
    // The API would 404 a true stranger; this covers the render rule for a
    // user who can see but not edit (the UI never invents rights).
    await renderDetail({ user: stranger })
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show history' })).toBeInTheDocument()
  })

  it('admin: everything, including assignee and delete', async () => {
    await renderDetail({ user: admin })
    expect(screen.getByLabelText('Status')).toBeInTheDocument()
    expect(screen.getByLabelText('Assignee')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })
})

// --- Status, priority, assignee ------------------------------------------

describe('status control', () => {
  it('offers only the current status and its legal transitions', async () => {
    // Mirrors TRANSITIONS: from resolved you can only reopen or close.
    await renderDetail({ ticket: makeTicket({ status: 'resolved' }) })
    const options = [...screen.getByLabelText('Status').options].map((o) => o.value)
    expect(options).toEqual(['resolved', 'open', 'closed'])
  })

  it('patches the status, applies the response, keeps comments, and notifies the parent', async () => {
    const comments = [{ id: 1, body: 'Existing', author: { id: 2, email: 'owner@example.com' }, created_at: new Date().toISOString() }]
    const { onChanged } = await renderDetail({ ticket: makeTicket({ comments }) })

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'in_progress' } })

    await waitFor(() =>
      expect(screen.getByText('In progress', { selector: '.badge' })).toHaveClass('badge--status-in_progress'),
    )
    expect(api.updateTicket).toHaveBeenCalledWith(12, { status: 'in_progress' })
    // The PATCH response (which has no comments) is merged over the loaded
    // ticket, so the thread survives without a refetch.
    expect(screen.getByText('Existing')).toBeInTheDocument()
    expect(api.getTicket).toHaveBeenCalledTimes(1)
    expect(onChanged).toHaveBeenCalledOnce()
  })

  it('disables the controls while a patch is in flight', async () => {
    const pending = deferred()
    api.updateTicket.mockReturnValue(pending.promise)
    await renderDetail({ user: admin })

    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: '1' } })
    expect(screen.getByLabelText('Status')).toBeDisabled()
    expect(screen.getByLabelText('Priority')).toBeDisabled()
    expect(screen.getByLabelText('Assignee')).toBeDisabled()

    pending.resolve({ ...makeTicket(), priority: 1 })
    await waitFor(() => expect(screen.getByLabelText('Status')).toBeEnabled())
  })

  it('shows the API error and re-enables the controls when a patch fails', async () => {
    api.updateTicket.mockRejectedValue(new Error('Cannot move a ticket from open to closed'))
    const { onChanged } = await renderDetail()

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'closed' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot move a ticket from open to closed')
    expect(screen.getByLabelText('Status')).toBeEnabled()
    expect(onChanged).not.toHaveBeenCalled()
  })
})

describe('priority and assignee controls', () => {
  it('sends the priority as a number', async () => {
    await renderDetail()
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: '1' } })
    await waitFor(() => expect(api.updateTicket).toHaveBeenCalledWith(12, { priority: 1 }))
  })

  it('sends a numeric assignee id, and null to unassign', async () => {
    await renderDetail({ user: admin, ticket: makeTicket({ assignee: { id: 3, email: 'agent@example.com' } }) })
    expect(screen.getByLabelText('Assignee')).toHaveValue('3')

    fireEvent.change(screen.getByLabelText('Assignee'), { target: { value: '1' } })
    await waitFor(() => expect(api.updateTicket).toHaveBeenCalledWith(12, { assignee_id: 1 }))

    fireEvent.change(screen.getByLabelText('Assignee'), { target: { value: '' } })
    await waitFor(() => expect(api.updateTicket).toHaveBeenCalledWith(12, { assignee_id: null }))
  })
})

// --- Inline editing ---------------------------------------------------------

describe('edit details', () => {
  it('opens a form prefilled from the ticket and cancels without a request', async () => {
    await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: 'Edit details' }))

    expect(screen.getByLabelText('Title')).toHaveValue('MFA prompt loop')
    expect(screen.getByLabelText('Description')).toHaveValue('Authenticator prompts endlessly.')
    expect(screen.getByLabelText('Category')).toHaveValue('1')
    // The status/priority controls give way to the form while editing.
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Status')).toBeInTheDocument()
    expect(api.updateTicket).not.toHaveBeenCalled()
  })

  it('saves title, description, and a numeric or null category, then closes', async () => {
    await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: 'Edit details' }))

    await userEvent.clear(screen.getByLabelText('Title'))
    await userEvent.type(screen.getByLabelText('Title'), 'MFA loop on new phone')
    await userEvent.selectOptions(screen.getByLabelText('Category'), '')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(api.updateTicket).toHaveBeenCalledWith(12, {
        title: 'MFA loop on new phone',
        description: 'Authenticator prompts endlessly.',
        category_id: null,
      }),
    )
    // Closed on success, and the header reflects the response.
    expect(await screen.findByRole('heading', { level: 2, name: '#12 MFA loop on new phone' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
  })

  it('keeps the form open and shows the error when saving fails', async () => {
    api.updateTicket.mockRejectedValue(new Error('must not be blank'))
    await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: 'Edit details' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('must not be blank')
    expect(screen.getByLabelText('Title')).toBeInTheDocument()
  })
})

// --- History ----------------------------------------------------------------

describe('history', () => {
  it('loads entries on demand, renders them, and toggles closed', async () => {
    api.getAuditLog.mockResolvedValue([
      { id: 1, field: 'assignee', old_value: null, new_value: 'agent@example.com', actor: { email: 'admin@example.com' }, created_at: new Date().toISOString() },
      { id: 2, field: 'status', old_value: 'new', new_value: 'open', actor: { email: 'admin@example.com' }, created_at: new Date().toISOString() },
    ])
    await renderDetail()
    expect(api.getAuditLog).not.toHaveBeenCalled() // lazy: only when asked

    fireEvent.click(screen.getByRole('button', { name: 'Show history' }))
    expect(await screen.findByRole('heading', { level: 3, name: 'History' })).toBeInTheDocument()
    const items = screen.getAllByRole('listitem').filter((li) => li.closest('.audit__list'))
    expect(items).toHaveLength(2)
    // Nulls render as a dash so "unassigned → agent" reads naturally.
    expect(items[0]).toHaveTextContent('assignee: — → agent@example.com')
    expect(items[1]).toHaveTextContent('status: new → open')
    expect(items[1]).toHaveTextContent('by admin@example.com')

    fireEvent.click(screen.getByRole('button', { name: 'Hide history' }))
    expect(screen.queryByRole('heading', { level: 3, name: 'History' })).not.toBeInTheDocument()
  })

  it('shows an empty state for a ticket with no changes', async () => {
    await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: 'Show history' }))
    expect(await screen.findByText('No changes yet.')).toBeInTheDocument()
  })

  it('refreshes the open history after a change', async () => {
    await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: 'Show history' }))
    await screen.findByText('No changes yet.')

    api.getAuditLog.mockResolvedValue([
      { id: 1, field: 'priority', old_value: 'P2', new_value: 'P1', actor: { email: 'owner@example.com' }, created_at: new Date().toISOString() },
    ])
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: '1' } })

    // The row's text is split across elements (label, values, meta), so
    // assert on the list item as a whole.
    await waitFor(() =>
      expect(document.querySelector('.audit__list li')).toHaveTextContent('priority: P2 → P1'),
    )
    expect(api.getAuditLog).toHaveBeenCalledTimes(2)
  })
})

// --- Comments ---------------------------------------------------------------

describe('comments', () => {
  it('posts a comment, clears the box, and reloads the thread', async () => {
    await renderDetail()
    api.addComment.mockResolvedValue({})
    api.getTicket.mockResolvedValue(
      makeTicket({ comments: [{ id: 5, body: 'Tried a reboot.', author: { id: 2, email: 'owner@example.com' }, created_at: new Date().toISOString() }] }),
    )

    await userEvent.type(screen.getByLabelText('Add a comment'), 'Tried a reboot.')
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))

    expect(await screen.findByRole('heading', { level: 3, name: 'Comments (1)' })).toBeInTheDocument()
    expect(api.addComment).toHaveBeenCalledWith(12, 'Tried a reboot.')
    expect(screen.getByLabelText('Add a comment')).toHaveValue('')
    expect(api.getTicket).toHaveBeenCalledTimes(2)
  })

  it('disables the button while posting', async () => {
    const pending = deferred()
    api.addComment.mockReturnValue(pending.promise)
    await renderDetail()

    await userEvent.type(screen.getByLabelText('Add a comment'), 'On it.')
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    expect(screen.getByRole('button', { name: 'Posting…' })).toBeDisabled()

    pending.resolve({})
    expect(await screen.findByRole('button', { name: 'Comment' })).toBeEnabled()
  })

  it('shows the error and keeps the draft when posting fails', async () => {
    api.addComment.mockRejectedValue(new Error('must not be blank'))
    await renderDetail()

    await userEvent.type(screen.getByLabelText('Add a comment'), '   ')
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('must not be blank')
    expect(screen.getByLabelText('Add a comment')).toHaveValue('   ')
  })
})

// --- Delete and navigation --------------------------------------------------

describe('delete', () => {
  it('asks for confirmation and does nothing when cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { onDeleted } = await renderDetail({ user: admin })

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(window.confirm).toHaveBeenCalledWith('Delete this ticket? This cannot be undone.')
    expect(api.deleteTicket).not.toHaveBeenCalled()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('deletes and reports to the parent when confirmed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.deleteTicket.mockResolvedValue(null)
    const { onDeleted } = await renderDetail({ user: admin })

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(onDeleted).toHaveBeenCalledOnce())
    expect(api.deleteTicket).toHaveBeenCalledWith(12)
  })

  it('shows the error when deletion fails', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.deleteTicket.mockRejectedValue(new Error('Admin access required'))
    const { onDeleted } = await renderDetail({ user: admin })

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Admin access required')
    expect(onDeleted).not.toHaveBeenCalled()
  })
})

describe('navigation', () => {
  it('Back reports to the parent', async () => {
    const { onBack } = await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: '← Back to tickets' }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
