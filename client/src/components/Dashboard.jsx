import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api'
import FilterBar from './FilterBar'
import Logo from './Logo'
import ThemeToggle from './ThemeToggle'
import TicketDetail from './TicketDetail'
import TicketForm from './TicketForm'
import TicketList from './TicketList'

const PAGE_SIZE = 20
const initialFilters = {
  scope: 'all',
  status: 'all',
  category_id: 'all',
  assignee_id: 'all',
  q: '',
  sort: '-created_at',
}

// The open ticket lives in the URL hash (#ticket-12) so refresh keeps the
// view, the back button closes it, and tickets can be deep-linked.
function ticketIdFromHash() {
  const match = /^#ticket-(\d+)$/.exec(window.location.hash)
  return match ? Number(match[1]) : null
}

function formatHours(hours) {
  if (hours == null) return '—'
  return hours < 48 ? `${Math.round(hours)}h` : `${(hours / 24).toFixed(1)}d`
}

function StatTile({ label, value, alert }) {
  return (
    <div className={`stat${alert && value > 0 ? ' stat--alert' : ''}`}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  )
}

function Dashboard({ user, onLogout }) {
  const [tickets, setTickets] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(initialFilters)
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [selectedId, setSelectedId] = useState(ticketIdFromHash)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  // Monotonic sequence so a slow, stale list response can never overwrite a
  // newer one.
  const requestSeq = useRef(0)

  useEffect(() => {
    const onHashChange = () => setSelectedId(ticketIdFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  function openTicket(id) {
    window.location.hash = `ticket-${id}`
  }

  function closeTicket() {
    window.location.hash = ''
  }

  const apiFilters = useCallback(() => {
    const { scope, ...rest } = filters
    if (scope === 'assigned') return { ...rest, assignee_id: user.id }
    if (scope === 'mine') return { ...rest, owner_id: user.id }
    return rest
  }, [filters, user.id])

  const loadStats = useCallback(() => {
    api.getStats().then(setStats).catch(() => setStats(null))
  }, [])

  const loadTickets = useCallback(
    async ({ nextOffset = 0, append = false } = {}) => {
      const seq = ++requestSeq.current
      setError(null)
      if (append) setLoadingMore(true)
      try {
        const page = await api.listTickets({ ...apiFilters(), limit: PAGE_SIZE, offset: nextOffset })
        if (seq !== requestSeq.current) return // a newer request superseded this one
        setTickets((prev) => (append ? [...prev, ...page.items] : page.items))
        setTotal(page.total)
        setOffset(nextOffset)
      } catch (err) {
        if (seq !== requestSeq.current) return
        // A network failure means the API server is likely down; an ApiError
        // means it answered (401s are already handled globally by App).
        setError(
          err instanceof ApiError
            ? err.message
            : `${err.message} — is the API server running? Start it with uvicorn app.main:app --reload.`,
        )
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [apiFilters],
  )

  const refresh = useCallback(() => {
    loadTickets()
    loadStats()
  }, [loadTickets, loadStats])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => setCategories([]))
    if (user.is_admin) {
      api.listUsers().then(setUsers).catch(() => setUsers([]))
    }
  }, [user.is_admin])

  async function handleCreate(input) {
    await api.createTicket(input)
    refresh()
  }

  return (
    <div className="page">
      <header className="header">
        <div className="header__brand">
          <Logo />
          <div>
            <h1>Ticket System</h1>
            <p className="header__subtitle">Track, triage, and resolve issues.</p>
          </div>
        </div>
        <div className="header__side">
          <span className="header__count">
            {total} ticket{total === 1 ? '' : 's'}
          </span>
          <span className="header__user">
            {user.email}
            {user.is_admin && <span className="badge badge--admin">admin</span>}
          </span>
          <ThemeToggle />
          <button className="btn--link" type="button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      <main className="content">
        {selectedId ? (
          <TicketDetail
            ticketId={selectedId}
            user={user}
            users={users}
            categories={categories}
            onBack={closeTicket}
            onChanged={refresh}
            onDeleted={() => {
              closeTicket()
              refresh()
            }}
          />
        ) : (
          <>
            {stats && (
              <div className="stats-row" role="status" aria-label="Queue summary">
                <StatTile label="Unresolved" value={stats.unresolved} />
                <StatTile label="New" value={stats.by_status.new} />
                <StatTile label="P1 urgent" value={stats.p1_unresolved} alert />
                <StatTile label="Unassigned" value={stats.unassigned_unresolved} />
                <StatTile label="Overdue" value={stats.overdue} alert />
                <StatTile label="Avg resolution" value={formatHours(stats.avg_resolution_hours)} />
              </div>
            )}

            <TicketForm categories={categories} onCreate={handleCreate} />
            <FilterBar
              filters={filters}
              categories={categories}
              users={users}
              isAdmin={user.is_admin}
              onChange={setFilters}
            />

            {error && (
              <div className="banner banner--error" role="alert">
                {error}
              </div>
            )}

            {loading ? (
              <p className="empty" role="status">
                Loading tickets…
              </p>
            ) : (
              <>
                <TicketList tickets={tickets} onSelect={openTicket} />
                {tickets.length < total && (
                  <div className="list-footer">
                    <span className="list-footer__count" role="status">
                      Showing {tickets.length} of {total}
                    </span>
                    <button
                      className="btn btn--primary"
                      type="button"
                      disabled={loadingMore}
                      onClick={() => loadTickets({ nextOffset: offset + PAGE_SIZE, append: true })}
                    >
                      {loadingMore ? 'Loading…' : 'Load more'}
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default Dashboard
