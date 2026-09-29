// Root component: decides which of three screens to show based on auth state.
//
//   checking   -> a stored token is being validated against /users/me
//   bootError  -> the API could not be reached (token kept, retry offered)
//   !user      -> no valid session: the login/register page
//   user       -> the dashboard
//
// A 401 on any later request is routed back here via the unauthorized
// handler, so an expired session always lands on the login page cleanly.
//
// The API sleeps between visits on its free-tier host and takes a while to
// wake, so the first request of a visit often fails. Two things absorb
// that: every visit pings /health immediately, which starts the wake-up
// before the visitor has typed anything, and both that ping and the token
// check retry on their own for a few minutes while telling the user what is
// happening. Only after the attempts are used up does an error with a
// manual Retry appear.
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, getToken, setToken, setUnauthorizedHandler } from './api'

// 8 attempts, 10 s apart, each allowed REQUEST_TIMEOUT_MS: a cold start of
// up to three minutes or so resolves without the user doing anything.
export const BOOT_ATTEMPTS = 8
export const BOOT_RETRY_MS = 10_000

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Any failure that is not "your token is bad" means the server did not give
// a usable answer — unreachable, timed out, or a 5xx — and is worth retrying.
const isBadToken = (err) => err instanceof ApiError && err.status === 401
import AuthPage from './components/AuthPage'
import Dashboard from './components/Dashboard'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(Boolean(getToken()))
  const [bootError, setBootError] = useState(null)
  // 'ok' | 'waking' | 'unreachable' — what the login page tells the visitor
  // about the server while they have no session.
  const [serverState, setServerState] = useState('ok')
  // Which retry the token check is on (0 = first try); drives the status text.
  const [attempt, setAttempt] = useState(0)
  // Set on unmount so an in-flight retry loop stops touching state.
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const loadUser = useCallback(async () => {
    if (!getToken()) return
    setChecking(true)
    setBootError(null)
    for (let n = 0; n < BOOT_ATTEMPTS; n += 1) {
      try {
        const me = await api.me()
        if (alive.current) setUser(me)
        break
      } catch (err) {
        if (isBadToken(err)) {
          setToken(null) // expired or invalid token — sign in again
          break
        }
        if (n + 1 < BOOT_ATTEMPTS) {
          if (alive.current) setAttempt(n + 1)
          await sleep(BOOT_RETRY_MS)
          if (!alive.current) return
        } else if (alive.current) {
          // Attempts used up: keep the token, offer a manual retry.
          setBootError(err.message)
        }
      }
    }
    if (alive.current) {
      setAttempt(0)
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    loadUser()
  }, [loadUser])

  // Warm the server up on every visit, and keep the login page informed.
  // Fire-and-forget: nothing waits on it, so a healthy server costs one
  // cheap request and a sleeping one starts waking before the first click.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      for (let n = 0; n < BOOT_ATTEMPTS && !cancelled; n += 1) {
        try {
          await api.health()
          if (!cancelled) setServerState('ok')
          return
        } catch {
          if (cancelled) return
          setServerState(n + 1 < BOOT_ATTEMPTS ? 'waking' : 'unreachable')
          if (n + 1 < BOOT_ATTEMPTS) await sleep(BOOT_RETRY_MS)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleLogout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  // Any 401 mid-session (expired token) signs the user out globally.
  useEffect(() => {
    setUnauthorizedHandler(handleLogout)
    return () => setUnauthorizedHandler(null)
  }, [handleLogout])

  if (checking) {
    return (
      <p className="empty" role="status">
        {attempt === 0
          ? 'Loading…'
          : `Waking up the server… this can take a minute or two (attempt ${attempt + 1} of ${BOOT_ATTEMPTS})`}
      </p>
    )
  }
  if (bootError) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Ticket System</h1>
          <p className="auth-card__error">
            Couldn't reach the API server ({bootError}).
            {import.meta.env.DEV && (
              <>
                {' '}
                Is it running? Start it with <code>uvicorn app.main:app --reload</code>.
              </>
            )}
          </p>
          <button className="btn btn--primary btn--block" type="button" onClick={loadUser}>
            Retry
          </button>
        </div>
      </div>
    )
  }
  if (!user) {
    return <AuthPage onAuthed={setUser} serverState={serverState} />
  }
  return <Dashboard user={user} onLogout={handleLogout} />
}

export default App
