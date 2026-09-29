// The root component's auth bootstrap: which of four screens shows, based
// on whether a token exists and what /users/me says about it. The child
// screens are replaced with stubs so these tests cover App's own logic —
// the state machine, token clearing, retry, and the global 401 handler —
// and nothing else.
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const user = { id: 1, email: 'joyce@example.com', is_admin: false }

// In-memory stand-in for localStorage so getToken/setToken behave.
let storedToken = null

vi.mock('../api', () => ({
  ApiError: class ApiError extends Error {
    constructor(message, status) {
      super(message)
      this.status = status
    }
  },
  api: { me: vi.fn(), health: vi.fn() },
  getToken: vi.fn(() => storedToken),
  setToken: vi.fn((t) => {
    storedToken = t
  }),
  setUnauthorizedHandler: vi.fn(),
}))

// Stub the screens: each renders a marker plus the one callback App wires.
vi.mock('../components/AuthPage', () => ({
  default: ({ onAuthed, serverState }) => (
    <div>
      <button type="button" onClick={() => onAuthed(user)}>
        stub-auth-page
      </button>
      <span>server:{serverState}</span>
    </div>
  ),
}))
vi.mock('../components/Dashboard', () => ({
  default: ({ user: u, onLogout }) => (
    <div>
      <span>stub-dashboard:{u.email}</span>
      <button type="button" onClick={onLogout}>
        stub-logout
      </button>
    </div>
  ),
}))

import App, { BOOT_ATTEMPTS, BOOT_RETRY_MS } from '../App'
import { ApiError, api, setToken, setUnauthorizedHandler } from '../api'

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.clearAllMocks()
  storedToken = null
  api.me.mockResolvedValue(user)
  api.health.mockResolvedValue({ status: 'ok' })
})

afterEach(() => {
  vi.useRealTimers()
})

// With fake timers, let pending promises and zero-delay timers settle.
const flush = () => act(() => vi.advanceTimersByTimeAsync(0))
// Advance past one retry delay and let the next attempt run.
const nextAttempt = () => act(() => vi.advanceTimersByTimeAsync(BOOT_RETRY_MS))

// --- The four screens -------------------------------------------------------

describe('bootstrap', () => {
  it('shows the auth page immediately when there is no token', () => {
    render(<App />)
    expect(screen.getByText('stub-auth-page')).toBeInTheDocument()
    // No token means nothing to validate; /users/me is never called.
    expect(api.me).not.toHaveBeenCalled()
  })

  it('validates a stored token and lands on the dashboard', async () => {
    storedToken = 'tok-1'
    const pending = deferred()
    api.me.mockReturnValue(pending.promise)
    render(<App />)

    // While the token is being checked, neither screen is shown.
    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    expect(screen.queryByText('stub-auth-page')).not.toBeInTheDocument()

    pending.resolve(user)
    expect(await screen.findByText('stub-dashboard:joyce@example.com')).toBeInTheDocument()
    expect(api.me).toHaveBeenCalledOnce()
  })

  it('clears an invalid or expired token and shows the auth page', async () => {
    // A 401 from /users/me means the token is dead: drop it so the next
    // load doesn't retry it, and go to login. No retry screen.
    storedToken = 'expired'
    api.me.mockRejectedValue(new ApiError('Could not validate credentials', 401))
    render(<App />)

    expect(await screen.findByText('stub-auth-page')).toBeInTheDocument()
    expect(setToken).toHaveBeenCalledWith(null)
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('retries on its own while the server wakes, then offers a manual retry', async () => {
    // A network failure is not a bad token. Distinguishing the two is the
    // point: the user should not be logged out because the API was down.
    // And a sleeping host is the common case, so the first failures are
    // retried quietly with a status line instead of an error.
    vi.useFakeTimers()
    storedToken = 'tok-1'
    api.me.mockRejectedValue(new Error('Failed to fetch'))
    render(<App />)
    await flush()

    expect(screen.getByRole('status')).toHaveTextContent(`attempt 2 of ${BOOT_ATTEMPTS}`)
    expect(screen.queryByText(/Couldn't reach/)).not.toBeInTheDocument()

    for (let n = 2; n <= BOOT_ATTEMPTS; n += 1) await nextAttempt()

    expect(api.me).toHaveBeenCalledTimes(BOOT_ATTEMPTS)
    expect(screen.getByText(/Couldn't reach the API server/)).toBeInTheDocument()
    expect(screen.getByText(/Failed to fetch/)).toBeInTheDocument()
    expect(setToken).not.toHaveBeenCalledWith(null)

    // Manual retry re-validates the same token; once the server answers,
    // the dashboard renders without a fresh login.
    api.me.mockResolvedValue(user)
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await flush()
    expect(screen.getByText('stub-dashboard:joyce@example.com')).toBeInTheDocument()
    expect(api.me).toHaveBeenCalledTimes(BOOT_ATTEMPTS + 1)
  })

  it('lands on the dashboard by itself once a later attempt succeeds', async () => {
    vi.useFakeTimers()
    storedToken = 'tok-1'
    api.me
      .mockRejectedValueOnce(new Error('Failed to fetch'))
      .mockRejectedValueOnce(new Error('Failed to fetch'))
      .mockResolvedValue(user)
    render(<App />)
    await flush()
    await nextAttempt()
    await nextAttempt()

    expect(screen.getByText('stub-dashboard:joyce@example.com')).toBeInTheDocument()
    expect(api.me).toHaveBeenCalledTimes(3)
    expect(screen.queryByText(/Couldn't reach/)).not.toBeInTheDocument()
  })

  it('treats a non-401 API error like an outage, not a dead token', async () => {
    vi.useFakeTimers()
    storedToken = 'tok-1'
    api.me.mockRejectedValue(new ApiError('Database unavailable', 503))
    render(<App />)
    await flush()
    for (let n = 2; n <= BOOT_ATTEMPTS; n += 1) await nextAttempt()

    expect(screen.getByText(/Couldn't reach the API server/)).toBeInTheDocument()
    expect(setToken).not.toHaveBeenCalledWith(null)
  })
})

// --- Warming the server up --------------------------------------------------

describe('warm-up ping', () => {
  it('pings /health on every visit, even without a token', async () => {
    render(<App />)
    await act(async () => {})
    expect(api.health).toHaveBeenCalledTimes(1)
    expect(screen.getByText('server:ok')).toBeInTheDocument()
  })

  it('tells the login page the server is waking, then that it is back', async () => {
    vi.useFakeTimers()
    api.health.mockRejectedValueOnce(new Error('Failed to fetch')).mockResolvedValue({ status: 'ok' })
    render(<App />)
    await flush()
    expect(screen.getByText('server:waking')).toBeInTheDocument()

    await nextAttempt()
    expect(screen.getByText('server:ok')).toBeInTheDocument()
    expect(api.health).toHaveBeenCalledTimes(2)
  })

  it('reports the server unreachable once the attempts are used up', async () => {
    vi.useFakeTimers()
    api.health.mockRejectedValue(new Error('Failed to fetch'))
    render(<App />)
    await flush()
    for (let n = 2; n <= BOOT_ATTEMPTS; n += 1) await nextAttempt()

    expect(screen.getByText('server:unreachable')).toBeInTheDocument()
    expect(api.health).toHaveBeenCalledTimes(BOOT_ATTEMPTS)
    // And it stops: no further attempts after the last one.
    await nextAttempt()
    expect(api.health).toHaveBeenCalledTimes(BOOT_ATTEMPTS)
  })
})

// --- Transitions between screens ------------------------------------------

describe('sign in and sign out', () => {
  it('moves from the auth page to the dashboard when the child reports a user', async () => {
    render(<App />)
    fireEvent.click(screen.getByText('stub-auth-page'))
    expect(await screen.findByText('stub-dashboard:joyce@example.com')).toBeInTheDocument()
  })

  it('signs out: clears the token and returns to the auth page', async () => {
    storedToken = 'tok-1'
    render(<App />)
    await screen.findByText('stub-dashboard:joyce@example.com')

    fireEvent.click(screen.getByRole('button', { name: 'stub-logout' }))
    expect(await screen.findByText('stub-auth-page')).toBeInTheDocument()
    expect(setToken).toHaveBeenCalledWith(null)
  })
})

// --- The global 401 handler -------------------------------------------------

describe('unauthorized handler', () => {
  it('registers sign-out with the network layer on mount and clears it on unmount', async () => {
    storedToken = 'tok-1'
    const { unmount } = render(<App />)
    await screen.findByText('stub-dashboard:joyce@example.com')

    // The network layer calls this on any mid-session 401 (expired token).
    const handler = setUnauthorizedHandler.mock.calls.at(-1)[0]
    expect(typeof handler).toBe('function')

    unmount()
    expect(setUnauthorizedHandler).toHaveBeenLastCalledWith(null)
  })

  it('signs the user out when the network layer reports a 401', async () => {
    storedToken = 'tok-1'
    render(<App />)
    await screen.findByText('stub-dashboard:joyce@example.com')

    const handler = setUnauthorizedHandler.mock.calls.at(-1)[0]
    handler()

    expect(await screen.findByText('stub-auth-page')).toBeInTheDocument()
    expect(setToken).toHaveBeenCalledWith(null)
  })
})
