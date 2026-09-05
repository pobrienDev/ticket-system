// Root component: decides which of three screens to show based on auth state.
//
//   checking   -> a stored token is being validated against /users/me
//   bootError  -> the API could not be reached (token kept, retry offered)
//   !user      -> no valid session: the login/register page
//   user       -> the dashboard
//
// A 401 on any later request is routed back here via the unauthorized
// handler, so an expired session always lands on the login page cleanly.
import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, getToken, setToken, setUnauthorizedHandler } from './api'
import AuthPage from './components/AuthPage'
import Dashboard from './components/Dashboard'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(Boolean(getToken()))
  const [bootError, setBootError] = useState(null)

  const loadUser = useCallback(async () => {
    if (!getToken()) return
    setChecking(true)
    setBootError(null)
    try {
      setUser(await api.me())
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setToken(null) // expired or invalid token — sign in again
      } else {
        // Server unreachable or transient failure: keep the token, offer retry.
        setBootError(err.message)
      }
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    loadUser()
  }, [loadUser])

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
        Loading…
      </p>
    )
  }
  if (bootError) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Ticket System</h1>
          <p className="auth-card__error">
            Couldn't reach the API server ({bootError}). Is it running? Start it with{' '}
            <code>uvicorn app.main:app --reload</code>.
          </p>
          <button className="btn btn--primary btn--block" type="button" onClick={loadUser}>
            Retry
          </button>
        </div>
      </div>
    )
  }
  if (!user) {
    return <AuthPage onAuthed={setUser} />
  }
  return <Dashboard user={user} onLogout={handleLogout} />
}

export default App
