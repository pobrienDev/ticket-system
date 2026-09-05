// The entire network layer: one request() helper plus a typed map of API
// calls. Components never touch fetch directly, so auth headers, error
// shaping, and 401 handling live in exactly one place.

const TOKEN_KEY = 'ticket_token'

// Same-origin by default (the Vite dev proxy forwards to the API). For a
// separately-hosted frontend, set VITE_API_URL to the backend's origin at
// build time and add that frontend origin to the backend's CORS_ORIGINS.
const API_BASE = import.meta.env.VITE_API_URL ?? ''

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// Called on any 401 outside the auth endpoints (i.e. an expired or revoked
// token mid-session) so the app can sign the user out instead of leaving
// them on a broken dashboard. Registered by App on mount.
let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

// FastAPI error bodies come in two shapes: a plain string `detail` from
// HTTPException, or an array of validation errors (422). Both are flattened
// to one human-readable message so components can just display err.message.
function detailToMessage(data, status) {
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail)) {
    return data.detail.map((d) => d.msg ?? JSON.stringify(d)).join('; ')
  }
  return `Request failed (${status})`
}

async function request(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(form).toString()
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload })
  if (res.status === 401 && !path.startsWith('/auth/') && unauthorizedHandler) {
    unauthorizedHandler()
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(detailToMessage(data, res.status), res.status)
  return data
}

export const api = {
  register: (email, password) => request('/auth/register', { method: 'POST', body: { email, password } }),
  // OAuth2 password flow: FastAPI expects form-encoded username/password
  login: (email, password) => request('/auth/login', { method: 'POST', form: { username: email, password } }),
  me: () => request('/users/me'),
  listUsers: () => request('/users'),
  listCategories: () => request('/categories'),
  listTickets: (filters = {}) => {
    // Only meaningful filters become query params; '' / null / 'all' mean
    // "no filter" in the UI and are dropped rather than sent.
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) {
      if (value !== '' && value !== null && value !== undefined && value !== 'all') {
        params.set(key, value)
      }
    }
    const query = params.toString()
    return request(`/tickets${query ? `?${query}` : ''}`)
  },
  getStats: () => request('/tickets/stats'),
  getTicket: (id) => request(`/tickets/${id}`),
  createTicket: (input) => request('/tickets', { method: 'POST', body: input }),
  updateTicket: (id, patch) => request(`/tickets/${id}`, { method: 'PATCH', body: patch }),
  deleteTicket: (id) => request(`/tickets/${id}`, { method: 'DELETE' }),
  addComment: (ticketId, body) =>
    request(`/tickets/${ticketId}/comments`, { method: 'POST', body: { body } }),
  getAuditLog: (ticketId) => request(`/tickets/${ticketId}/audit`),
}
