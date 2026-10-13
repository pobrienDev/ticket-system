// Single-ticket view: header/badges, status-priority-assignee controls,
// an inline edit form for title/description/category, the audit history,
// and comments. Every change goes through applyPatch so in-flight state,
// error display, and list/stats refresh are handled once.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { LIMITS, PRIORITIES, TRANSITIONS, formatDate, statusLabel } from '../constants'
import TicketBadges from './TicketBadges'

function TicketDetail({ ticketId, user, users, categories, onBack, onChanged, onDeleted }) {
  const [ticket, setTicket] = useState(null)
  const [auditLog, setAuditLog] = useState(null)
  const [comment, setComment] = useState('')
  const [commenting, setCommenting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editForm, setEditForm] = useState(null) // null = not editing
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .getTicket(ticketId)
      .then((loaded) => {
        if (!cancelled) setTicket(loaded)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [ticketId])

  async function applyPatch(patch) {
    setError(null)
    setSaving(true)
    let updated
    try {
      updated = await api.updateTicket(ticketId, patch)
    } catch (err) {
      setError(err.message)
      setSaving(false)
      return false
    }
    // The PATCH response is the fresh ticket; keep the loaded comments.
    setTicket((prev) => ({ ...updated, comments: prev?.comments ?? [] }))
    setSaving(false)
    onChanged()
    // History is a secondary view: refresh it if it is open, but a failure
    // there must not be reported as a failed save — the save succeeded.
    if (auditLog !== null) api.getAuditLog(ticketId).then(setAuditLog).catch(() => {})
    return true
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
      setTicket(await api.getTicket(ticketId))
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
        <p className="empty" role={error ? 'alert' : 'status'}>
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
  const statusOptions = [ticket.status, ...(TRANSITIONS[ticket.status] ?? [])]

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
                maxLength={LIMITS.title}
                required
              />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                rows={4}
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                maxLength={LIMITS.description}
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
              <TicketBadges ticket={ticket} />
              <h2>
                #{ticket.id} {ticket.title}
              </h2>
            </div>

            {ticket.description && <p className="detail__description">{ticket.description}</p>}
            <p className="ticket-card__meta">
              Opened by {ticket.owner.email} on {formatDate(ticket.created_at)} ·{' '}
              {ticket.assignee ? `assigned to ${ticket.assignee.email}` : 'unassigned'}
              {ticket.due_date && ` · due ${formatDate(ticket.due_date)}`}
              {ticket.resolved_at && ` · resolved ${formatDate(ticket.resolved_at)}`}
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
                      by {entry.actor.email} on {formatDate(entry.created_at)}
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
                  {c.author.email} · {formatDate(c.created_at)}
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
              maxLength={LIMITS.comment}
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
