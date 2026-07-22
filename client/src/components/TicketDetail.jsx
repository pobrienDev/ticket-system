import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { PRIORITIES, STATUSES, priorityLabel } from '../constants'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function TicketDetail({ ticketId, user, users, onBack, onChanged, onDeleted }) {
  const [ticket, setTicket] = useState(null)
  const [auditLog, setAuditLog] = useState(null)
  const [comment, setComment] = useState('')
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
    try {
      await api.updateTicket(ticketId, patch)
      await load()
      if (auditLog !== null) setAuditLog(await api.getAuditLog(ticketId))
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddComment(event) {
    event.preventDefault()
    setError(null)
    try {
      await api.addComment(ticketId, comment)
      setComment('')
      await load()
    } catch (err) {
      setError(err.message)
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
        <p className="empty">{error ?? 'Loading ticket…'}</p>
      </div>
    )
  }

  const canEdit = user.is_admin || ticket.owner.id === user.id

  return (
    <div className="detail">
      <button className="btn--link" type="button" onClick={onBack}>
        ← Back to tickets
      </button>

      <div className="detail__card">
        <div className="ticket-card__title-row">
          <span className={`badge badge--p${ticket.priority}`}>{priorityLabel(ticket.priority)}</span>
          {ticket.category && <span className="badge badge--category">{ticket.category.name}</span>}
          <h2>
            #{ticket.id} {ticket.title}
          </h2>
        </div>

        {ticket.description && <p className="detail__description">{ticket.description}</p>}
        <p className="ticket-card__meta">
          Opened by {ticket.owner.email} on {dateFormat.format(new Date(ticket.created_at))} ·{' '}
          {ticket.assignee ? `assigned to ${ticket.assignee.email}` : 'unassigned'}
        </p>

        <div className="detail__controls">
          {canEdit && (
            <>
              <label className="field">
                <span>Status</span>
                <select
                  value={ticket.status}
                  onChange={(e) => applyPatch({ status: e.target.value })}
                >
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Priority</span>
                <select
                  value={ticket.priority}
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

          {user.is_admin && (
            <label className="field">
              <span>Assignee</span>
              <select
                value={ticket.assignee?.id ?? ''}
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
              <p className="empty">No status or assignment changes yet.</p>
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
              required
            />
          </label>
          <button className="btn btn--primary" type="submit">
            Comment
          </button>
        </form>
      </div>
    </div>
  )
}

export default TicketDetail
