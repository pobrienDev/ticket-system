import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, getToken, setToken, setUnauthorizedHandler } from '../api'

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('token storage', () => {
  it('stores, returns, and clears the token', () => {
    setToken('abc')
    expect(getToken()).toBe('abc')
    setToken(null)
    expect(getToken()).toBeNull()
  })

  it('sends the token as a bearer header when present', async () => {
    setToken('tok-123')
    fetch.mockResolvedValue(jsonResponse({ id: 1 }))
    await api.me()
    const [, options] = fetch.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer tok-123')
  })
})

describe('error handling', () => {
  it('surfaces a string detail as the error message', async () => {
    fetch.mockResolvedValue(jsonResponse({ detail: 'Ticket not found' }, 404))
    await expect(api.getTicket(999)).rejects.toThrow('Ticket not found')
    await expect(api.getTicket(999)).rejects.toBeInstanceOf(ApiError)
  })

  it('joins validation-error arrays into one message', async () => {
    fetch.mockResolvedValue(
      jsonResponse({ detail: [{ msg: 'too short' }, { msg: 'too long' }] }, 422),
    )
    await expect(api.createTicket({})).rejects.toThrow('too short; too long')
  })

  it('falls back to the status code when the body is not JSON', async () => {
    fetch.mockResolvedValue({ ok: false, status: 500, json: () => Promise.reject(new Error('nope')) })
    await expect(api.listTickets()).rejects.toThrow('Request failed (500)')
  })

  it('returns null for 204 responses', async () => {
    fetch.mockResolvedValue({ ok: true, status: 204, json: () => Promise.reject(new Error('empty')) })
    await expect(api.deleteTicket(1)).resolves.toBeNull()
  })
})

describe('401 handling', () => {
  it('invokes the unauthorized handler on a mid-session 401', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetch.mockResolvedValue(jsonResponse({ detail: 'Could not validate credentials' }, 401))
    await expect(api.listTickets()).rejects.toThrow()
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('does not sign the user out for a failed login attempt', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetch.mockResolvedValue(jsonResponse({ detail: 'Incorrect email or password' }, 401))
    await expect(api.login('a@b.com', 'wrong')).rejects.toThrow()
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('query building', () => {
  it('drops empty and "all" filter values', async () => {
    fetch.mockResolvedValue(jsonResponse({ items: [], total: 0 }))
    await api.listTickets({ status: 'all', q: '', category_id: 2, limit: 20 })
    const [url] = fetch.mock.calls[0]
    expect(url).toBe('/tickets?category_id=2&limit=20')
  })
})
