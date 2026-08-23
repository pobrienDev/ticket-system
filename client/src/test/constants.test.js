import { describe, expect, it } from 'vitest'
import { PRIORITIES, STATUSES, TRANSITIONS, isOverdue, priorityLabel, statusLabel } from '../constants'

describe('status transitions', () => {
  it('covers every status exactly once', () => {
    const statusValues = STATUSES.map((s) => s.value)
    expect(Object.keys(TRANSITIONS).sort()).toEqual([...statusValues].sort())
  })

  it('only ever targets known statuses and never the current one', () => {
    const statusValues = new Set(STATUSES.map((s) => s.value))
    for (const [from, targets] of Object.entries(TRANSITIONS)) {
      expect(targets).not.toContain(from)
      for (const to of targets) expect(statusValues.has(to)).toBe(true)
    }
  })

  it('forces closed tickets to reopen before anything else', () => {
    expect(TRANSITIONS.closed).toEqual(['open'])
  })
})

describe('labels', () => {
  it('maps known values and falls back for unknown ones', () => {
    expect(statusLabel('in_progress')).toBe('In progress')
    expect(statusLabel('mystery')).toBe('mystery')
    expect(priorityLabel(1)).toBe('P1 — Critical')
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
    expect(isOverdue({ status: 'open', due_date: past })).toBe(true)
    expect(isOverdue({ status: 'new', due_date: past })).toBe(true)
    expect(isOverdue({ status: 'open', due_date: future })).toBe(false)
    expect(isOverdue({ status: 'resolved', due_date: past })).toBe(false)
    expect(isOverdue({ status: 'closed', due_date: past })).toBe(false)
    expect(isOverdue({ status: 'open', due_date: null })).toBe(false)
  })
})
