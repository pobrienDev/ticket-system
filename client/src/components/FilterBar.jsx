// Queue controls: scope chips, search, status/category/assignee filters, and
// sort. Stateless apart from the search buffer — every change is reported
// to the Dashboard as a new filters object.
import { useEffect, useState } from 'react'
import { STATUSES } from '../constants'

const SCOPES = [
  { value: 'all', label: 'All tickets' },
  { value: 'assigned', label: 'Assigned to me' },
  { value: 'mine', label: 'Opened by me' },
]

function FilterBar({ filters, categories, users, isAdmin, onChange }) {
  // Search input is buffered locally and debounced so we don't fire one API
  // request per keystroke.
  const [search, setSearch] = useState(filters.q)

  useEffect(() => {
    setSearch(filters.q)
  }, [filters.q])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== filters.q) onChange({ ...filters, q: search })
    }, 300)
    return () => clearTimeout(timer)
  }, [search, filters, onChange])

  function setFilter(field, value) {
    onChange({ ...filters, [field]: value })
  }

  return (
    <div className="filter-bar">
      <div className="chips" role="group" aria-label="Ticket scope">
        {SCOPES.map((scope) => (
          <button
            key={scope.value}
            type="button"
            className={`chip${filters.scope === scope.value ? ' chip--active' : ''}`}
            onClick={() => setFilter('scope', scope.value)}
          >
            {scope.label}
          </button>
        ))}
      </div>

      <div className="filter-bar__fields">
        <label className="field field--grow">
          <span>Search</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title or description…"
          />
        </label>

        <label className="field">
          <span>Status</span>
          <select value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="all">All</option>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Category</span>
          <select value={filters.category_id} onChange={(e) => setFilter('category_id', e.target.value)}>
            <option value="all">All</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        {isAdmin && (
          <label className="field">
            <span>Assignee</span>
            <select
              value={filters.assignee_id}
              onChange={(e) => setFilter('assignee_id', e.target.value)}
              disabled={filters.scope === 'assigned'}
            >
              <option value="all">All</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="field">
          <span>Sort</span>
          <select value={filters.sort} onChange={(e) => setFilter('sort', e.target.value)}>
            <option value="-created_at">Newest first</option>
            <option value="created_at">Oldest first</option>
            <option value="priority">Priority (P1 first)</option>
            <option value="-priority">Priority (P5 first)</option>
            <option value="due_date">Due soonest</option>
          </select>
        </label>
      </div>
    </div>
  )
}

export default FilterBar
