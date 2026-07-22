import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import FilterBar from './FilterBar'
import TicketDetail from './TicketDetail'
import TicketForm from './TicketForm'
import TicketList from './TicketList'

const initialFilters = { status: 'all', category_id: 'all', q: '', sort: '-created_at' }

function Dashboard({ user, onLogout }) {
  const [tickets, setTickets] = useState([])
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState(initialFilters)
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadTickets = useCallback(async () => {
    setError(null)
    try {
      const page = await api.listTickets({ ...filters, limit: 50 })
      setTickets(page.items)
      setTotal(page.total)
    } catch (err) {
      // A network failure means the API server is likely down; an ApiError
      // means it answered (401s are already handled globally by App).
      setError(
        err instanceof ApiError
          ? err.message
          : `${err.message} — is the API server running? Start it with uvicorn app.main:app --reload.`,
      )
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    loadTickets()
  }, [loadTickets])

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => setCategories([]))
    if (user.is_admin) {
      api.listUsers().then(setUsers).catch(() => setUsers([]))
    }
  }, [user.is_admin])

  async function handleCreate(input) {
    await api.createTicket(input)
    await loadTickets()
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Ticket System</h1>
          <p className="header__subtitle">Track, triage, and resolve issues.</p>
        </div>
        <div className="header__side">
          <span className="header__count">
            {total} ticket{total === 1 ? '' : 's'}
          </span>
          <span className="header__user">
            {user.email}
            {user.is_admin && <span className="badge badge--admin">admin</span>}
          </span>
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
            onBack={() => setSelectedId(null)}
            onChanged={loadTickets}
            onDeleted={() => {
              setSelectedId(null)
              loadTickets()
            }}
          />
        ) : (
          <>
            <TicketForm categories={categories} onCreate={handleCreate} />
            <FilterBar filters={filters} categories={categories} onChange={setFilters} />

            {error && (
              <div className="banner banner--error" role="alert">
                {error}
              </div>
            )}

            {loading ? (
              <p className="empty">Loading tickets…</p>
            ) : (
              <TicketList tickets={tickets} onSelect={setSelectedId} />
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default Dashboard
