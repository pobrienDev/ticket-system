// Single-ticket view: header/badges, status-priority-assignee controls,
// an inline edit form for title/description/category, the audit history,
// and comments. Every change goes through applyPatch so in-flight state,
// error display, and list/stats refresh are handled once.
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { PRIORITIES, TRANSITIONS, isOverdue, priorityLabel, statusLabel } from '../constants'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function TicketDetail({ ticketId, user, users, categories, onBack, onChanged, onDeleted }) {
  const [ticket, setTicket] = useState(null)
  const [auditLog, setAuditLog] = useState(null)
  const [comment, setComment] = useState('')
  const [commenting, setCommenting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editForm, setEditForm] = useState(null) // null = not editing
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setTicket(await api.getTicket(ticketId))
    } catch (err) {
      setError(err.message)
    }
  }, [ticketId])

  useEffect(() => {
    load()
  }, [load])

  async function applyPatch(patch) {
    setError(null)
    setSaving(true)
    try {
      const updated = await api.updateTicket(ticketId, patch)
      // The PATCH response is the fresh ticket; keep the loaded comments.
      setTicket((prev) => ({ ...updated, comments: prev?.comments ?? [] }))
      if (auditLog !== null) setAuditLog(await api.getAuditLog(ticketId))
      onChanged()
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveEdit(event) {
    event.preventDefault()
    const ok = await applyPatch({
      title: editForm.title,
      description: editForm.description,
      category_id: editForm.category_id === '' ? null : Number(editForm.category_id),
    })
    if (ok) setEditForm(null)
  }

  async function handleAddComment(event) {
    event.preventDefault()
    setError(null)
    setCommenting(true)
    try {
      await api.addComment(ticketId, comment)
      setComment('')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setCommenting(false)
    }
  }

  async function toggleAudit() {
    if (auditLog !== null) {
      setAuditLog(null)
      return
    }
    try {
      setAuditLog(await api.getAuditLog(ticketId))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete() {
    if (!window.confirm('Delete this ticket? This cannot be undone.')) return
    try {
      await api.deleteTicket(ticketId)
      onDeleted()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!ticket) {
    return (
      <div className="detail">
        <button className="btn--link" type="button" onClick={onBack}>
          ← Back to tickets
        </button>
        <p className="empty" role="status">
          {error ?? 'Loading ticket…'}
        </p>
      </div>
    )
  }

  // Mirrors the backend's edit rule (owner, assignee, or admin). The API
  // enforces it regardless; this only decides whether to render controls.
  const canEdit = user.is_admin || ticket.owner.id === user.id || ticket.assignee?.id === user.id
  // The status select offers only legal next states, so the UI can't even
  // express a transition the server would reject with a 409.
  const statusOptions = [ticket.status, ...TRANSITIONS[ticket.status]]
  const overdue = isOverdue(ticket)

  return (
    <div className="detail">
      <button className="btn--link" type="button" onClick={onBack}>
        ← Back to tickets
      </button>

      <div className="detail__card">
        {editForm ? (
          <form className="detail__edit" onSubmit={handleSaveEdit}>
            <label className="field field--grow">
              <span>Title</span>
              <input
                type="text"
                value={editForm.title}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                maxLength={200}
                required
              />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                rows={4}
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Category</span>
              <select
                value={editForm.category_id}
                onChange={(e) => setEditForm({ ...editForm, category_id: e.target.value })}
              >
                <option value="">No category</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="detail__edit-buttons">
              <button className="btn btn--primary" type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </button>
              <button className="btn--link" type="button" onClick={() => setEditForm(null)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <div className="ticket-card__title-row">
              <span className={`badge badge--p${ticket.priority}`}>{priorityLabel(ticket.priority)}</span>
              <span className={`badge badge--status badge--status-${ticket.status}`}>
                {statusLabel(ticket.status)}
              </span>
              {overdue && <span className="badge badge--overdue">Overdue</span>}
              {ticket.category && <span className="badge badge--category">{ticket.category.name}</span>}
              <h2>
                #{ticket.id} {ticket.title}
              </h2>
            </div>

            {ticket.description && <p className="detail__description">{ticket.description}</p>}
            <p className="ticket-card__meta">
              Opened by {ticket.owner.email} on {dateFormat.format(new Date(ticket.created_at))} ·{' '}
              {ticket.assignee ? `assigned to ${ticket.assignee.email}` : 'unassigned'}
              {ticket.due_date && ` · due ${dateFormat.format(new Date(ticket.due_date))}`}
              {ticket.resolved_at && ` · resolved ${dateFormat.format(new Date(ticket.resolved_at))}`}
            </p>
          </>
        )}

        <div className="detail__controls">
          {canEdit && !editForm && (
            <>
              <label className="field">
                <span>Status</span>
                <select
                  value={ticket.status}
                  disabled={saving}
                  onChange={(e) => applyPatch({ status: e.target.value })}
                >
                  {statusOptions.map((value) => (
                    <option key={value} value={value}>
                      {statusLabel(value)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Priority</span>
                <select
                  value={ticket.priority}
                  disabled={saving}
                  onChange={(e) => applyPatch({ priority: Number(e.target.value) })}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}

          {user.is_admin && !editForm && (
            <label className="field">
              <span>Assignee</span>
              <select
                value={ticket.assignee?.id ?? ''}
                disabled={saving}
                onChange={(e) =>
                  applyPatch({ assignee_id: e.target.value === '' ? null : Number(e.target.value) })
                }
              >
                <option value="">Unassigned</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.email}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="detail__control-buttons">
            {canEdit && !editForm && (
              <button
                className="btn--link"
                type="button"
                onClick={() =>
                  setEditForm({
                    title: ticket.title,
                    description: ticket.description,
                    category_id: ticket.category?.id ?? '',
                  })
                }
              >
                Edit details
              </button>
            )}
            <button className="btn--link" type="button" onClick={toggleAudit}>
              {auditLog === null ? 'Show history' : 'Hide history'}
            </button>
            {user.is_admin && (
              <button className="btn btn--danger" type="button" onClick={handleDelete}>
                Delete
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="banner banner--error" role="alert">
            {error}
          </div>
        )}

        {auditLog !== null && (
          <div className="audit">
            <h3>History</h3>
            {auditLog.length === 0 ? (
              <p className="empty">No changes yet.</p>
            ) : (
              <ul className="audit__list">
                {auditLog.map((entry) => (
                  <li key={entry.id}>
                    <strong>{entry.field}</strong>: {entry.old_value ?? '—'} →{' '}
                    {entry.new_value ?? '—'}
                    <span className="audit__meta">
                      {' '}
                      by {entry.actor.email} on {dateFormat.format(new Date(entry.created_at))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="detail__card">
        <h3>
          Comments ({ticket.comments.length})
        </h3>
        {ticket.comments.length === 0 ? (
          <p className="empty">No comments yet.</p>
        ) : (
          <ul className="comments">
            {ticket.comments.map((c) => (
              <li key={c.id} className="comment">
                <p className="comment__body">{c.body}</p>
                <p className="comment__meta">
                  {c.author.email} · {dateFormat.format(new Date(c.created_at))}
                </p>
              </li>
            ))}
          </ul>
        )}

        <form className="comment-form" onSubmit={handleAddComment}>
          <label className="field field--grow">
            <span>Add a comment</span>
            <textarea
              rows={2}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="What did you try? What changed?"
              maxLength={5000}
              required
            />
          </label>
          <button className="btn btn--primary" type="submit" disabled={commenting}>
            {commenting ? 'Posting…' : 'Comment'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default TicketDetail
