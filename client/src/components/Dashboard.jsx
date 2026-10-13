// The main authenticated screen. Owns the queue state (filters, tickets,
// pagination, stats) and switches between the list view and TicketDetail.
// Child components are presentational and report intent upward through
// callbacks; all API access for the list view happens here.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import FilterBar from './FilterBar'
import Logo from './Logo'
import ThemeToggle from './ThemeToggle'
import TicketDetail from './TicketDetail'
import TicketForm from './TicketForm'
import TicketList from './TicketList'

const PAGE_SIZE = 20
// '' in a select means "no filter"; the network layer drops it. The scope
// chip is a UI concept translated into an id filter by queryFor.
const initialFilters = {
  scope: 'all',
  status: '',
  category_id: '',
  assignee_id: '',
  q: '',
  sort: '-created_at',
}

// The open ticket lives in the URL hash (#ticket-12) so refresh keeps the
// view, the back button closes it, and tickets can be deep-linked. Cards are
// plain links to that hash.
function ticketIdFromHash() {
  const match = /^#ticket-(\d+)$/.exec(window.location.hash)
  return match ? Number(match[1]) : null
}

function queryFor(filters, userId) {
  const { scope, ...rest } = filters
  if (scope === 'assigned') return { ...rest, assignee_id: userId }
  if (scope === 'mine') return { ...rest, owner_id: userId }
  return rest
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
  const [tickets, setTickets] = useState(null) // null until the first page arrives
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(initialFilters)
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [selectedId, setSelectedId] = useState(ticketIdFromHash)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  // Bumped by mutations so the first page reloads with the current filters.
  const [listVersion, setListVersion] = useState(0)
  // Request bookkeeping. Every first-page request takes a number; a response
  // is applied only if it is still the newest, so a slow, stale page can
  // never overwrite a newer one. shownSeq is the request whose page is on
  // screen; loadMore uses it to refuse to extend a page that is being
  // replaced.
  const resetSeq = useRef(0)
  const shownSeq = useRef(0)
  const appendSeq = useRef(0)

  useEffect(() => {
    const onHashChange = () => setSelectedId(ticketIdFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  function closeTicket() {
    window.location.hash = ''
  }

  // First page, whenever the filters change or a mutation asks for a reload.
  useEffect(() => {
    const seq = ++resetSeq.current
    api
      .listTickets({ ...queryFor(filters, user.id), limit: PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (seq !== resetSeq.current) return // a newer request superseded this one
        shownSeq.current = seq
        setTickets(page.items)
        setTotal(page.total)
        setError(null)
      })
      .catch((err) => {
        if (seq === resetSeq.current) setError(err.message)
      })
  }, [filters, user.id, listVersion])

  // Stats cover everything the user can see, so they do not depend on the
  // filters: loaded once, then only when a mutation may have changed them.
  const loadStats = useCallback(() => {
    api.getStats().then(setStats).catch(() => setStats(null))
  }, [])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => setCategories([]))
    if (user.is_admin) {
      api.listUsers().then(setUsers).catch(() => setUsers([]))
    }
  }, [user.is_admin])

  // Any mutation (create, patch, delete) can change both the list and the
  // stats tiles, so they are always refreshed together.
  function refresh() {
    setListVersion((version) => version + 1)
    loadStats()
  }

  async function handleCreate(input) {
    await api.createTicket(input)
    refresh()
  }

  async function loadMore() {
    // While a first page is still loading, the list on screen belongs to the
    // previous filters; appending the new filters' page 2 to it would mix
    // two queries. Ignore the click until the new page has landed.
    if (shownSeq.current !== resetSeq.current) return
    const base = resetSeq.current
    const seq = ++appendSeq.current
    setLoadingMore(true)
    try {
      const page = await api.listTickets({
        ...queryFor(filters, user.id),
        limit: PAGE_SIZE,
        offset: tickets.length,
      })
      if (base !== resetSeq.current || seq !== appendSeq.current) return
      setTickets((prev) => [...prev, ...page.items])
      setTotal(page.total)
    } catch (err) {
      if (base === resetSeq.current) setError(err.message)
    } finally {
      setLoadingMore(false)
    }
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
          // key: a different ticket is a fresh component, so nothing (an
          // open edit form, a loaded ticket) carries over between tickets.
          <TicketDetail
            key={selectedId}
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

            {tickets === null ? (
              !error && (
                <p className="empty" role="status">
                  Loading tickets…
                </p>
              )
            ) : (
              <>
                <TicketList tickets={tickets} />
                {tickets.length < total && (
                  <div className="list-footer">
                    <span className="list-footer__count" role="status">
                      Showing {tickets.length} of {total}
                    </span>
                    <button className="btn btn--primary" type="button" disabled={loadingMore} onClick={loadMore}>
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
