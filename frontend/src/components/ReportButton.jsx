import { useState } from 'react'
import { api } from '../api'
import { FieldError } from './Status.jsx'

function ReportButton({ commentId }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)

  if (sent) return <p className="meta">Thanks, a moderator will review this.</p>

  if (!open) {
    return (
      <button type="button" className="link-button" onClick={() => setOpen(true)}>
        Report
      </button>
    )
  }

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      await api(`/comments/${commentId}/report`, { method: 'POST', body: { reason } })
      setSent(true)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="report-form" onSubmit={submit}>
      <label>
        Why are you reporting this comment?
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows="2"
          required
        />
      </label>
      <div className="form-actions">
        <button type="submit">Send report</button>
        <button type="button" className="link-button" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      <FieldError messages={error} />
    </form>
  )
}

export default ReportButton
