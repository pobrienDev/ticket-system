export const STATUSES = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
]

// Matches the backend: integer priority, 1 = highest.
export const PRIORITIES = [
  { value: 1, label: 'P1 — Critical' },
  { value: 2, label: 'P2 — High' },
  { value: 3, label: 'P3 — Medium' },
  { value: 4, label: 'P4 — Low' },
  { value: 5, label: 'P5 — Backlog' },
]

export function statusLabel(value) {
  return STATUSES.find((s) => s.value === value)?.label ?? value
}

export function priorityLabel(value) {
  return PRIORITIES.find((p) => p.value === value)?.label ?? `P${value}`
}
