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

beforeEach(() => {
  vi.clearAllMocks()
  api.login.mockResolvedValue({ access_token: 'tok-1' })
  api.me.mockResolvedValue(user)
  api.register.mockResolvedValue(user)
})

describe('AuthPage', () => {
  it('logs in, stores the token, and reports the user', async () => {
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await userEvent.type(screen.getByLabelText('Email'), 'joyce@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'longenough123')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(api.login).toHaveBeenCalledWith('joyce@example.com', 'longenough123')
    expect(api.register).not.toHaveBeenCalled()
    expect(setToken).toHaveBeenCalledWith('tok-1')
    expect(onAuthed).toHaveBeenCalledWith(user)
  })

  it('registers first when in register mode', async () => {
    render(<AuthPage onAuthed={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Need an account? Register' }))
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'longenough123')
    await userEvent.click(screen.getByRole('button', { name: 'Register' }))

    expect(api.register).toHaveBeenCalledWith('new@example.com', 'longenough123')
    expect(api.login).toHaveBeenCalled()
  })

  it('shows the API error and does not authenticate on failure', async () => {
    api.login.mockRejectedValue(new Error('Incorrect email or password'))
    const onAuthed = vi.fn()
    render(<AuthPage onAuthed={onAuthed} />)

    await userEvent.type(screen.getByLabelText('Email'), 'joyce@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrongpassword')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()
    expect(onAuthed).not.toHaveBeenCalled()
  })
})
