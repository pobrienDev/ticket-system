// The light/dark switch. Small, but it decides the starting theme from two
// sources with a precedence rule (an explicit choice beats the OS), applies
// the choice to <html> for the stylesheet, and persists it without letting
// a storage failure break the toggle.
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ThemeToggle from '../components/ThemeToggle'

// jsdom has no matchMedia; this installs one that reports the given OS
// preference for the dark-scheme query.
function stubOsPreference(prefersDark) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query) => ({ matches: prefersDark && query.includes('dark'), media: query })),
  )
}

beforeEach(() => {
  delete document.documentElement.dataset.theme
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  delete document.documentElement.dataset.theme
})

// --- Starting theme ---------------------------------------------------------

describe('initial theme', () => {
  it('defaults to light when there is no stored choice and no OS signal', () => {
    // jsdom exposes no matchMedia at all; the optional call falls through
    // to light rather than throwing.
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toHaveTextContent('🌙')
  })

  it('follows the OS preference when nothing was chosen explicitly', () => {
    stubOsPreference(true)
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toHaveTextContent('☀️')
  })

  it('lets an explicit choice on <html> override the OS preference', () => {
    // index.html applies a stored choice to data-theme before first paint;
    // the toggle must reflect that, not the OS, or the icon would lie.
    stubOsPreference(true)
    document.documentElement.dataset.theme = 'light'
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument()
  })
})

// --- Toggling ---------------------------------------------------------------

describe('toggling', () => {
  it('applies the theme to <html>, persists it, and flips the control', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button', { name: 'Switch to dark mode' })

    fireEvent.click(button)
    // The stylesheet keys off data-theme; the choice must survive reloads.
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(button).toHaveAccessibleName('Switch to light mode')
    expect(button).toHaveTextContent('☀️')

    fireEvent.click(button)
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('theme')).toBe('light')
    expect(button).toHaveAccessibleName('Switch to dark mode')
  })

  it('still switches the theme when storage is unavailable', () => {
    // Private browsing or blocked storage throws on setItem. The visible
    // theme must still change for this visit; only persistence is lost.
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    render(<ThemeToggle />)

    expect(() => fireEvent.click(screen.getByRole('button'))).not.toThrow()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
  })

  it('exposes its purpose through an accessible name and a tooltip', () => {
    // The visible content is an emoji, so the name for assistive tech (and
    // the hover title for everyone else) carries the meaning.
    render(<ThemeToggle />)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-label', 'Switch to dark mode')
    expect(button).toHaveAttribute('title', 'Switch to dark mode')
  })
})
