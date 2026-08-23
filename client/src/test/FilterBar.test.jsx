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

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('FilterBar', () => {
  it('debounces search input instead of firing per keystroke', () => {
    const onChange = vi.fn()
    render(<FilterBar filters={baseFilters} categories={[]} users={[]} isAdmin={false} onChange={onChange} />)

    const search = screen.getByLabelText('Search')
    fireEvent.change(search, { target: { value: 'p' } })
    fireEvent.change(search, { target: { value: 'pr' } })
    fireEvent.change(search, { target: { value: 'printer' } })
    expect(onChange).not.toHaveBeenCalled()

    vi.advanceTimersByTime(350)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ ...baseFilters, q: 'printer' })
  })

  it('switches scope via the chips', () => {
    const onChange = vi.fn()
    render(<FilterBar filters={baseFilters} categories={[]} users={[]} isAdmin={false} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Assigned to me' }))
    expect(onChange).toHaveBeenCalledWith({ ...baseFilters, scope: 'assigned' })
  })

  it('only offers the assignee filter to admins', () => {
    const { rerender } = render(
      <FilterBar filters={baseFilters} categories={[]} users={[]} isAdmin={false} onChange={() => {}} />,
    )
    expect(screen.queryByLabelText('Assignee')).not.toBeInTheDocument()

    rerender(
      <FilterBar
        filters={baseFilters}
        categories={[]}
        users={[{ id: 2, email: 'agent@example.com' }]}
        isAdmin={true}
        onChange={() => {}}
      />,
    )
    expect(screen.getByLabelText('Assignee')).toBeInTheDocument()
    expect(screen.getByText('agent@example.com')).toBeInTheDocument()
  })
})
