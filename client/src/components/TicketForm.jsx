// New-ticket form. A controlled form holding string values from the inputs;
// the numeric/nullable conversions happen once at submit so the API always
// receives the types it expects (priority as a number, category_id or null).
import { useState } from 'react'
import { PRIORITIES } from '../constants'

const emptyForm = { title: '', description: '', priority: 3, category_id: '' }

function TicketForm({ categories, onCreate }) {
  const [form, setForm] = useState(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  function setField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await onCreate({
        title: form.title,
        description: form.description,
        priority: Number(form.priority),
        category_id: form.category_id === '' ? null : Number(form.category_id),
      })
      setForm(emptyForm)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="ticket-form" onSubmit={handleSubmit}>
      <h2>New ticket</h2>

      <div className="ticket-form__row">
        <label className="field field--grow">
          <span>Title</span>
          <input
            type="text"
            value={form.title}
            onChange={(e) => setField('title', e.target.value)}
            placeholder="Short summary of the issue"
            maxLength={200}
            required
          />
        </label>

        <label className="field">
          <span>Priority</span>
          <select value={form.priority} onChange={(e) => setField('priority', e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Category</span>
          <select value={form.category_id} onChange={(e) => setField('category_id', e.target.value)}>
            <option value="">No category</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="field">
        <span>Description</span>
        <textarea
          rows={3}
          value={form.description}
          onChange={(e) => setField('description', e.target.value)}
          placeholder="Steps to reproduce, expected behavior, context…"
        />
      </label>

      {error && <p className="ticket-form__error">{error}</p>}

      <button className="btn btn--primary" type="submit" disabled={submitting}>
        {submitting ? 'Creating…' : 'Create ticket'}
      </button>
    </form>
  )
}

export default TicketForm
