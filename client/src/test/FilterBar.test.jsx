// The queue controls. FilterBar is stateless apart from the search buffer:
// every change is reported upward as a whole new filters object. These
// tests cover the debounce (with fake timers, so timing is exact), the
// immediate controls, the scope chips, and the admin-only assignee filter.
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FilterBar from '../components/FilterBar'

const baseFilters = {
  scope: 'all',
  status: 'all',
  category_id: 'all',
  assignee_id: 'all',
  q: '',
  sort: '-created_at',
}

const categories = [
  { id: 1, name: 'Printer' },
  { id: 2, name: 'Network' },
]
const users = [{ id: 2, email: 'agent@example.com' }]

function renderBar(props = {}) {
  const onChange = vi.fn()
  const utils = render(
    <FilterBar
      filters={baseFilters}
      categories={categories}
      users={[]}
      isAdmin={false}
      onChange={onChange}
      {...props}
    />,
  )
  return { onChange, ...utils }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

// --- Search (debounced) -----------------------------------------------------

describe('search', () => {
  it('debounces input instead of firing per keystroke', () => {
    const { onChange } = renderBar()
    const search = screen.getByLabelText('Search')

    fireEvent.change(search, { target: { value: 'p' } })
    fireEvent.change(search, { target: { value: 'pr' } })
    fireEvent.change(search, { target: { value: 'printer' } })
    expect(onChange).not.toHaveBeenCalled()

    vi.advanceTimersByTime(350)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ ...baseFilters, q: 'printer' })
  })

  it('restarts the timer on every keystroke', () => {
    // The effect cleanup clears the pending timer each time the value
    // changes, so the call fires 300 ms after the LAST keystroke, not the
    // first. Two keystrokes 200 ms apart therefore produce one call at
    // ~500 ms, never one at 300 ms.
    const { onChange } = renderBar()
    const search = screen.getByLabelText('Search')

    fireEvent.change(search, { target: { value: 'p' } })
    vi.advanceTimersByTime(200)
    fireEvent.change(search, { target: { value: 'pr' } })
    vi.advanceTimersByTime(200) // 400 ms since the first keystroke, 200 since the last
    expect(onChange).not.toHaveBeenCalled()

    vi.advanceTimersByTime(150)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ ...baseFilters, q: 'pr' })
  })

  it('does not report a value that matches the filter already applied', () => {
    // Typing and then deleting back to the current filter is not a change.
    const { onChange } = renderBar()
    const search = screen.getByLabelText('Search')

    fireEvent.change(search, { target: { value: 'x' } })
    fireEvent.change(search, { target: { value: '' } })
    vi.advanceTimersByTime(350)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('follows an external reset of the search filter', () => {
    // The parent owns the filters; if it clears q (a reset button, a scope
    // change), the box must show the new value rather than a stale draft.
    const { rerender } = renderBar({ filters: { ...baseFilters, q: 'printer' } })
    expect(screen.getByLabelText('Search')).toHaveValue('printer')

    rerender(
      <FilterBar filters={baseFilters} categories={categories} users={[]} isAdmin={false} onChange={() => {}} />,
    )
    expect(screen.getByLabelText('Search')).toHaveValue('')
  })
})

// --- Immediate controls -----------------------------------------------------

describe('select filters', () => {
  it('report status, category, and sort changes immediately', () => {
    // Only search is debounced; a select is a deliberate single action.
    const { onChange } = renderBar()

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'open' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...baseFilters, status: 'open' })

    fireEvent.change(screen.getByLabelText('Category'), { target: { value: '2' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...baseFilters, category_id: '2' })

    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'due_date' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...baseFilters, sort: 'due_date' })
    expect(onChange).toHaveBeenCalledTimes(3)
  })

  it('offers every status, every category, and every sort order', () => {
    renderBar()
    const options = (label) => [...screen.getByLabelText(label).options].map((o) => o.value)

    expect(options('Status')).toEqual(['all', 'new', 'open', 'in_progress', 'resolved', 'closed'])
    expect(options('Category')).toEqual(['all', '1', '2'])
    // Both priority directions and the SLA sort the backend supports.
    expect(options('Sort')).toEqual(['-created_at', 'created_at', 'priority', '-priority', 'due_date'])
  })
})

// --- Scope chips ------------------------------------------------------------

describe('scope chips', () => {
  it('switch scope and mark the active one', () => {
    const { onChange } = renderBar({ filters: { ...baseFilters, scope: 'assigned' } })

    // The current scope is styled active; the others are not.
    expect(screen.getByRole('button', { name: 'Assigned to me' })).toHaveClass('chip--active')
    expect(screen.getByRole('button', { name: 'All tickets' })).not.toHaveClass('chip--active')

    fireEvent.click(screen.getByRole('button', { name: 'Opened by me' }))
    expect(onChange).toHaveBeenCalledWith({ ...baseFilters, scope: 'mine' })
  })
})

// --- Admin-only assignee filter --------------------------------------------

describe('assignee filter', () => {
  it('is only offered to admins', () => {
    // Regular users can't list users, so the dropdown would be empty for
    // them; the "Assigned to me" chip covers their case.
    const { rerender } = renderBar()
    expect(screen.queryByLabelText('Assignee')).not.toBeInTheDocument()

    rerender(
      <FilterBar filters={baseFilters} categories={categories} users={users} isAdmin={true} onChange={() => {}} />,
    )
    expect(screen.getByLabelText('Assignee')).toBeInTheDocument()
    expect(screen.getByText('agent@example.com')).toBeInTheDocument()
  })

  it('reports the chosen assignee', () => {
    const { onChange } = renderBar({ users, isAdmin: true })
    fireEvent.change(screen.getByLabelText('Assignee'), { target: { value: '2' } })
    expect(onChange).toHaveBeenCalledWith({ ...baseFilters, assignee_id: '2' })
  })

  it('is disabled while "Assigned to me" is active', () => {
    // The chip already pins the assignee to the current user; letting the
    // dropdown contradict it would be a confusing no-op.
    renderBar({ users, isAdmin: true, filters: { ...baseFilters, scope: 'assigned' } })
    expect(screen.getByLabelText('Assignee')).toBeDisabled()
  })
})
