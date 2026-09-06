// The login/register form. The network layer is mocked at the module
// boundary, so these tests cover what the component owns: the two modes,
// the register-then-login sequence, token storage, error display, and the
// in-flight state that prevents double submission.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AuthPage from '../components/AuthPage'

vi.mock('../api', () => ({
  api: {
    login: vi.fn(),
    register: vi.fn(),
    me: vi.fn(),
  },
  setToken: vi.fn(),
}))

import { api, setToken } from '../api'

const user = { id: 1, email: 'joyce@example.com', is_admin: false }

// A promise the test resolves by hand, to observe the in-flight state.
function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}

async function fillAndSubmit(email, password, buttonName) {
  await userEvent.type(screen.getByLabelText('Email'), email)
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.click(screen.getByRole('button', { name: buttonName }))
}

beforeEach(() => {
  vi.clearAllMocks()
  api.login.mockResolvedValue({ access_token: 'tok-1' })
  api.me.mockResolvedValue(user)
  api.register.mockResolvedValue(user)
})

// --- Sign in ----------------------------------------------------------------

describe('signing in', () => {
  it('logs in, stores the token, then loads and reports the user', async () => {
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await fillAndSubmit('joyce@example.com', 'longenough123', 'Sign in')

    expect(api.login).toHaveBeenCalledWith('joyce@example.com', 'longenough123')
    expect(api.register).not.toHaveBeenCalled()
    expect(setToken).toHaveBeenCalledWith('tok-1')
    // The token must be stored before /users/me is called, because that
    // request needs it in the Authorization header.
    expect(setToken.mock.invocationCallOrder[0]).toBeLessThan(api.me.mock.invocationCallOrder[0])
    expect(onAuthed).toHaveBeenCalledWith(user)
  })

  it('shows the API error and does not authenticate on failure', async () => {
    api.login.mockRejectedValue(new Error('Incorrect email or password'))
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await fillAndSubmit('joyce@example.com', 'wrongpassword', 'Sign in')

    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()
    expect(setToken).not.toHaveBeenCalled()
    expect(onAuthed).not.toHaveBeenCalled()
  })

  it('reports an error if the profile fetch fails after login', async () => {
    // Login succeeded but /users/me did not (e.g. the server dropped
    // between requests): the user sees the error and is not signed in.
    api.me.mockRejectedValue(new Error('Request failed (503)'))
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await fillAndSubmit('joyce@example.com', 'longenough123', 'Sign in')

    expect(await screen.findByText('Request failed (503)')).toBeInTheDocument()
    expect(onAuthed).not.toHaveBeenCalled()
  })
})

// --- Register ---------------------------------------------------------------

describe('registering', () => {
  it('registers first, then logs in with the same credentials', async () => {
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await userEvent.click(screen.getByRole('button', { name: 'Need an account? Register' }))
    await fillAndSubmit('new@example.com', 'longenough123', 'Register')

    expect(api.register).toHaveBeenCalledWith('new@example.com', 'longenough123')
    expect(api.login).toHaveBeenCalledWith('new@example.com', 'longenough123')
    expect(api.register.mock.invocationCallOrder[0]).toBeLessThan(api.login.mock.invocationCallOrder[0])
    // The reported user comes from /users/me, the same as a plain sign-in.
    expect(onAuthed).toHaveBeenCalledWith(user)
  })

  it('shows the registration error and never attempts login', async () => {
    api.register.mockRejectedValue(new Error('Email already registered'))
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await userEvent.click(screen.getByRole('button', { name: 'Need an account? Register' }))
    await fillAndSubmit('taken@example.com', 'longenough123', 'Register')

    expect(await screen.findByText('Email already registered')).toBeInTheDocument()
    expect(api.login).not.toHaveBeenCalled()
    expect(onAuthed).not.toHaveBeenCalled()
  })
})

// --- Mode switching ---------------------------------------------------------

describe('switching modes', () => {
  it('swaps the copy, the submit label, and the password autocomplete hint', async () => {
    render(<AuthPage onAuthed={() => {}} />)
    const password = screen.getByLabelText('Password')

    expect(screen.getByText('Sign in to your account')).toBeInTheDocument()
    // current-password vs new-password tells password managers whether to
    // fill a saved credential or offer to generate one.
    expect(password).toHaveAttribute('autocomplete', 'current-password')

    await userEvent.click(screen.getByRole('button', { name: 'Need an account? Register' }))
    expect(screen.getByText('Create an account')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Register' })).toBeInTheDocument()
    expect(password).toHaveAttribute('autocomplete', 'new-password')

    await userEvent.click(screen.getByRole('button', { name: 'Have an account? Sign in' }))
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('clears a previous error when the mode changes', async () => {
    // A stale "wrong password" message under a fresh registration form
    // would be confusing; switching modes resets it.
    api.login.mockRejectedValue(new Error('Incorrect email or password'))
    render(<AuthPage onAuthed={() => {}} />)

    await fillAndSubmit('joyce@example.com', 'wrongpassword', 'Sign in')
    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Need an account? Register' }))
    expect(screen.queryByText('Incorrect email or password')).not.toBeInTheDocument()
  })
})

// --- In-flight state and form constraints -----------------------------------

describe('submission state', () => {
  it('disables the button and shows progress while a request is pending', async () => {
    // Guards against double submission (a second click would send a second
    // login, or two registrations).
    const pending = deferred()
    api.login.mockReturnValue(pending.promise)
    render(<AuthPage onAuthed={() => {}} />)

    await fillAndSubmit('joyce@example.com', 'longenough123', 'Sign in')

    const button = screen.getByRole('button', { name: 'Working…' })
    expect(button).toBeDisabled()

    pending.resolve({ access_token: 'tok-1' })
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('declares the browser-side constraints the API also enforces', () => {
    // required + minLength give instant feedback; the server still
    // validates (8–72 characters, valid email) regardless.
    render(<AuthPage onAuthed={() => {}} />)
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('Email')).toBeRequired()
    expect(screen.getByLabelText('Password')).toHaveAttribute('minlength', '8')
    expect(screen.getByLabelText('Password')).toBeRequired()
  })
})
