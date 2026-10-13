// Domain vocabulary shared by every component: status and priority lists,
// the status transition map, and small helpers derived from them. Values
// here must match the backend enums in app/models.py.

export const STATUSES = [
  { value: 'new', label: 'New' },
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
]

// Mirrors the backend's ALLOWED_TRANSITIONS: which statuses a ticket in a
// given status may move to. Resolved/closed tickets must be reopened first.
export const TRANSITIONS = {
  new: ['open', 'in_progress', 'resolved', 'closed'],
  open: ['in_progress', 'resolved', 'closed'],
  in_progress: ['open', 'resolved', 'closed'],
  resolved: ['open', 'closed'],
  closed: ['open'],
}

// Matches the backend: integer priority, 1 = highest.
export const PRIORITIES = [
  { value: 1, label: 'P1 — Critical' },
  { value: 2, label: 'P2 — High' },
  { value: 3, label: 'P3 — Medium' },
  { value: 4, label: 'P4 — Low' },
  { value: 5, label: 'P5 — Backlog' },
]

// Input limits mirrored from the API (app/schemas.py) so the browser stops
// a visitor at the same point the server would. The server remains the
// authority; these only make the limit visible before a request is sent.
export const LIMITS = {
  title: 200,
  description: 10_000,
  comment: 5_000,
  search: 200,
  passwordMin: 8,
  passwordMax: 72, // bytes on the server (bcrypt's cap); characters here, close enough
}

// API timestamps are UTC with an explicit offset; show them in the viewer's
// locale and timezone.
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function formatDate(iso) {
  return dateFormat.format(new Date(iso))
}

export function statusLabel(value) {
  return STATUSES.find((s) => s.value === value)?.label ?? value
}

export function priorityLabel(value) {
  return PRIORITIES.find((p) => p.value === value)?.label ?? `P${value}`
}

export function isOverdue(ticket) {
  return (
    Boolean(ticket.due_date) &&
    ticket.status !== 'resolved' &&
    ticket.status !== 'closed' &&
    new Date(ticket.due_date) < new Date()
  )
}
