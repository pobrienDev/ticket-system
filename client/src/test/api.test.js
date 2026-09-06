// The network layer in isolation: fetch is stubbed globally, so these tests
// pin the contract between components and the API — headers, encodings,
// endpoint paths, error shaping, and the 401 rule — without a server.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, getToken, setToken, setUnauthorizedHandler } from '../api'

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }
}

// The [url, options] pair fetch was last called with.
function lastRequest() {
  return fetch.mock.calls.at(-1)
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  fetch.mockResolvedValue(jsonResponse({}))
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

// --- Token storage and the Authorization header ----------------------------

describe('token storage', () => {
  it('stores, returns, and clears the token', () => {
    setToken('abc')
    expect(getToken()).toBe('abc')
    setToken(null)
    expect(getToken()).toBeNull()
  })

  it('sends the token as a bearer header when present', async () => {
    setToken('tok-123')
    await api.me()
    const [, options] = lastRequest()
    expect(options.headers.Authorization).toBe('Bearer tok-123')
  })

  it('sends no Authorization header when there is no token', async () => {
    await api.me()
    const [, options] = lastRequest()
    expect(options.headers.Authorization).toBeUndefined()
  })
})

// --- Request encoding -------------------------------------------------------

describe('request encoding', () => {
  it('sends JSON bodies with the JSON content type', async () => {
    await api.createTicket({ title: 'Printer jams', priority: 2 })
    const [url, options] = lastRequest()
    expect(url).toBe('/tickets')
    expect(options.method).toBe('POST')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({ title: 'Printer jams', priority: 2 })
  })

  it('sends login as a form-encoded OAuth2 password grant', async () => {
    // The one non-JSON request: FastAPI's OAuth2PasswordRequestForm expects
    // form fields named username/password, not a JSON body.
    await api.login('joyce@example.com', 'p@ss word')
    const [url, options] = lastRequest()
    expect(url).toBe('/auth/login')
    expect(options.headers['Content-Type']).toBe('application/x-www-form-urlencoded')
    expect(new URLSearchParams(options.body).get('username')).toBe('joyce@example.com')
    expect(new URLSearchParams(options.body).get('password')).toBe('p@ss word')
  })

  it('sends GET requests with no body or content type', async () => {
    await api.listCategories()
    const [, options] = lastRequest()
    expect(options.method).toBe('GET')
    expect(options.body).toBeUndefined()
    expect(options.headers['Content-Type']).toBeUndefined()
  })

  it('prefixes every path with VITE_API_URL when one is configured', async () => {
    // API_BASE is read at module load (Vite inlines import.meta.env), so the
    // module is re-imported with the variable stubbed. This is the switch
    // that lets a separately-hosted frontend reach the backend.
    vi.stubEnv('VITE_API_URL', 'https://api.example.com')
    vi.resetModules()
    const fresh = await import('../api')
    await fresh.api.me()
    expect(lastRequest()[0]).toBe('https://api.example.com/users/me')
    vi.unstubAllEnvs()
    vi.resetModules()
  })
})

// --- Endpoint map -----------------------------------------------------------

describe('endpoint map', () => {
  // The api object is the only place URLs live. Each entry pins the method
  // and path a call produces, so a typo can't silently hit the wrong route.
  it.each([
    ['me', () => api.me(), 'GET', '/users/me'],
    ['listUsers', () => api.listUsers(), 'GET', '/users'],
    ['listCategories', () => api.listCategories(), 'GET', '/categories'],
    ['getStats', () => api.getStats(), 'GET', '/tickets/stats'],
    ['getTicket', () => api.getTicket(12), 'GET', '/tickets/12'],
    ['updateTicket', () => api.updateTicket(12, { priority: 1 }), 'PATCH', '/tickets/12'],
    ['deleteTicket', () => api.deleteTicket(12), 'DELETE', '/tickets/12'],
    ['addComment', () => api.addComment(12, 'hi'), 'POST', '/tickets/12/comments'],
    ['getAuditLog', () => api.getAuditLog(12), 'GET', '/tickets/12/audit'],
    ['register', () => api.register('a@b.com', 'longenough123'), 'POST', '/auth/register'],
  ])('%s → %s %s', async (_name, call, method, path) => {
    await call()
    const [url, options] = lastRequest()
    expect(url).toBe(path)
    expect(options.method).toBe(method)
  })

  it('wraps a comment body in the shape the API expects', async () => {
    await api.addComment(12, 'Tried rebooting.')
    expect(JSON.parse(lastRequest()[1].body)).toEqual({ body: 'Tried rebooting.' })
  })
})

// --- Error shaping ----------------------------------------------------------

describe('error handling', () => {
  it('surfaces a string detail as an ApiError carrying the status', async () => {
    fetch.mockResolvedValue(jsonResponse({ detail: 'Ticket not found' }, 404))
    const error = await api.getTicket(999).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe('Ticket not found')
    expect(error.status).toBe(404)
  })

  it('joins validation-error arrays into one message', async () => {
    // FastAPI's 422 body is a list of {loc, msg, type}; components display
    // one string, so the messages are joined.
    fetch.mockResolvedValue(
      jsonResponse({ detail: [{ msg: 'too short' }, { msg: 'too long' }] }, 422),
    )
    await expect(api.createTicket({})).rejects.toThrow('too short; too long')
  })

  it('falls back to serializing validation items that have no msg', async () => {
    fetch.mockResolvedValue(jsonResponse({ detail: [{ loc: ['body', 'title'] }] }, 422))
    await expect(api.createTicket({})).rejects.toThrow('{"loc":["body","title"]}')
  })

  it('falls back to the status code when the body is not JSON', async () => {
    fetch.mockResolvedValue({ ok: false, status: 500, json: () => Promise.reject(new Error('nope')) })
    await expect(api.listTickets()).rejects.toThrow('Request failed (500)')
  })

  it('returns null for 204 responses', async () => {
    // DELETE returns no body; callers must not try to parse one.
    fetch.mockResolvedValue({ ok: true, status: 204, json: () => Promise.reject(new Error('empty')) })
    await expect(api.deleteTicket(1)).resolves.toBeNull()
  })
})

// --- The 401 rule -----------------------------------------------------------

describe('401 handling', () => {
  it('invokes the unauthorized handler on a mid-session 401', async () => {
    // An expired or revoked token on any protected request signs the user
    // out globally (App registers the handler) instead of leaving them on a
    // broken dashboard. The error is still thrown to the caller.
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetch.mockResolvedValue(jsonResponse({ detail: 'Could not validate credentials' }, 401))
    await expect(api.listTickets()).rejects.toThrow()
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('does not sign the user out for a failed login attempt', async () => {
    // A 401 from /auth/* means "wrong credentials", not "session expired";
    // treating it as a sign-out would clear the form the user is filling in.
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetch.mockResolvedValue(jsonResponse({ detail: 'Incorrect email or password' }, 401))
    await expect(api.login('a@b.com', 'wrong')).rejects.toThrow()
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

// --- Query building ---------------------------------------------------------

describe('query building', () => {
  it('drops empty and "all" filter values', async () => {
    fetch.mockResolvedValue(jsonResponse({ items: [], total: 0 }))
    await api.listTickets({ status: 'all', q: '', category_id: 2, limit: 20 })
    expect(lastRequest()[0]).toBe('/tickets?category_id=2&limit=20')
  })

  it('keeps zero and omits null or undefined values', async () => {
    // offset: 0 is falsy but meaningful (the first page); null/undefined
    // mean "no filter".
    fetch.mockResolvedValue(jsonResponse({ items: [], total: 0 }))
    await api.listTickets({ offset: 0, assignee_id: null, owner_id: undefined, sort: '-created_at' })
    expect(lastRequest()[0]).toBe('/tickets?offset=0&sort=-created_at')
  })

  it('sends a bare path when there are no filters', async () => {
    fetch.mockResolvedValue(jsonResponse({ items: [], total: 0 }))
    await api.listTickets()
    expect(lastRequest()[0]).toBe('/tickets')
  })
})
