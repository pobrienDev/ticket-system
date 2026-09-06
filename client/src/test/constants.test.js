// The frontend's copy of the domain vocabulary. These values mirror the
// backend enums and transition map in app/models.py; the tests here keep
// that mirror honest, since the two codebases can't import each other.
import { describe, expect, it } from 'vitest'
import { PRIORITIES, STATUSES, TRANSITIONS, isOverdue, priorityLabel, statusLabel } from '../constants'

describe('status list', () => {
  it('lists statuses in lifecycle order, starting with new', () => {
    // This order drives the status filter dropdown and reads as the
    // lifecycle: a ticket is untriaged, then worked, then finished.
    expect(STATUSES.map((s) => s.value)).toEqual(['new', 'open', 'in_progress', 'resolved', 'closed'])
  })
})

describe('status transitions', () => {
  it('matches the backend transition map exactly', () => {
    // Contract snapshot. This must equal models.ALLOWED_TRANSITIONS in
    // app/models.py; the backend's own test_lifecycle.py checks every pair
    // against that map. A change to the lifecycle is made in both places,
    // and this test is what flags a frontend that fell behind.
    expect(TRANSITIONS).toEqual({
      new: ['open', 'in_progress', 'resolved', 'closed'],
      open: ['in_progress', 'resolved', 'closed'],
      in_progress: ['open', 'resolved', 'closed'],
      resolved: ['open', 'closed'],
      closed: ['open'],
    })
  })

  it('covers every status exactly once', () => {
    const statusValues = STATUSES.map((s) => s.value)
    expect(Object.keys(TRANSITIONS).sort()).toEqual([...statusValues].sort())
  })

  it('only ever targets known statuses and never the current one', () => {
    // No self-transitions: re-selecting the current status is a no-op in the
    // UI (the select shows it as the current value, not an option to move to).
    const statusValues = new Set(STATUSES.map((s) => s.value))
    for (const [from, targets] of Object.entries(TRANSITIONS)) {
      expect(targets).not.toContain(from)
      for (const to of targets) expect(statusValues.has(to)).toBe(true)
    }
  })

  it('forces closed tickets to reopen before anything else', () => {
    expect(TRANSITIONS.closed).toEqual(['open'])
  })

  it('lets every unfinished status reach closed directly', () => {
    // Closing is always available while work is in flight (a duplicate, a
    // non-issue); only a closed ticket has to go through open first.
    for (const from of ['new', 'open', 'in_progress', 'resolved']) {
      expect(TRANSITIONS[from]).toContain('closed')
    }
  })
})

describe('priorities', () => {
  it('are the integers 1 through 5 with P-prefixed labels, 1 = highest', () => {
    // Matches the backend's ge=1, le=5 constraint and its "1 = highest"
    // convention; the labels are what the badges and selects display.
    expect(PRIORITIES.map((p) => p.value)).toEqual([1, 2, 3, 4, 5])
    for (const p of PRIORITIES) expect(p.label).toMatch(new RegExp(`^P${p.value} — `))
    expect(PRIORITIES[0].label).toBe('P1 — Critical')
  })
})

describe('labels', () => {
  it('maps known values and falls back for unknown ones', () => {
    expect(statusLabel('new')).toBe('New')
    expect(statusLabel('in_progress')).toBe('In progress')
    expect(priorityLabel(1)).toBe('P1 — Critical')
    // Unknown values render as-is rather than crashing, so an API that
    // gains a status before the client is updated still displays something.
    expect(statusLabel('mystery')).toBe('mystery')
    expect(priorityLabel(9)).toBe('P9')
  })

  it('has a label for every status and priority', () => {
    for (const s of STATUSES) expect(s.label).toBeTruthy()
    for (const p of PRIORITIES) expect(p.label).toBeTruthy()
  })
})

describe('isOverdue', () => {
  const past = new Date(Date.now() - 3600_000).toISOString()
  const future = new Date(Date.now() + 3600_000).toISOString()

  it('is true only for unresolved tickets past their due date', () => {
    // Mirrors the backend's overdue definition in the stats endpoint:
    // due_date in the past AND status not resolved/closed.
    expect(isOverdue({ status: 'new', due_date: past })).toBe(true)
    expect(isOverdue({ status: 'open', due_date: past })).toBe(true)
    expect(isOverdue({ status: 'in_progress', due_date: past })).toBe(true)
    expect(isOverdue({ status: 'open', due_date: future })).toBe(false)
  })

  it('is never true for finished tickets, however late', () => {
    expect(isOverdue({ status: 'resolved', due_date: past })).toBe(false)
    expect(isOverdue({ status: 'closed', due_date: past })).toBe(false)
  })

  it('is false when there is no due date', () => {
    expect(isOverdue({ status: 'open', due_date: null })).toBe(false)
    expect(isOverdue({ status: 'open' })).toBe(false)
  })
})
