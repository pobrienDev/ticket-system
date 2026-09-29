import { useState } from 'react'
import { api, setToken } from '../api'
import Logo from './Logo'
import ThemeToggle from './ThemeToggle'

// What the form says about the server while a visitor has no session. App
// owns the probing; this only renders the result, so a sleeping host reads
// as "waking up" rather than as a login that inexplicably hangs.
const SERVER_NOTICES = {
  waking: 'Waking up the server — this can take a minute or two. You can sign in once it responds.',
  unreachable: "The server isn't responding. Please try again in a minute.",
}

function AuthPage({ onAuthed, serverState = 'ok' }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'register') {
        await api.register(email, password)
      }
      const { access_token } = await api.login(email, password)
      setToken(access_token)
      onAuthed(await api.me())
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <ThemeToggle />
        <div className="auth-card__brand">
          <Logo />
          <h1>Ticket System</h1>
        </div>
        <p className="auth-card__subtitle">
          {mode === 'login' ? 'Sign in to your account' : 'Create an account'}
        </p>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            minLength={8}
            required
          />
        </label>

        {SERVER_NOTICES[serverState] && (
          <p className="auth-card__notice" role="status">
            {SERVER_NOTICES[serverState]}
          </p>
        )}
        {error && <p className="auth-card__error">{error}</p>}

        <button className="btn btn--primary btn--block" type="submit" disabled={submitting}>
          {submitting ? 'Working…' : mode === 'login' ? 'Sign in' : 'Register'}
        </button>

        <button
          className="btn--link"
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
        >
          {mode === 'login' ? 'Need an account? Register' : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  )
}

export default AuthPage
