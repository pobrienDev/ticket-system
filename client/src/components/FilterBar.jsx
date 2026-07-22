import { STATUSES } from '../constants'

function FilterBar({ filters, categories, onChange }) {
  function setFilter(field, value) {
    onChange({ ...filters, [field]: value })
  }

  return (
    <div className="filter-bar">
      <label className="field field--grow">
        <span>Search</span>
        <input
          type="search"
          value={filters.q}
          onChange={(e) => setFilter('q', e.target.value)}
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

      <label className="field">
        <span>Sort</span>
        <select value={filters.sort} onChange={(e) => setFilter('sort', e.target.value)}>
          <option value="-created_at">Newest first</option>
          <option value="created_at">Oldest first</option>
          <option value="priority">Priority (P1 first)</option>
        </select>
      </label>
    </div>
  )
}

export default FilterBar
