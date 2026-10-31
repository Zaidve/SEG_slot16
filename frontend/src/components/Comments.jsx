import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { formatDate } from '../format'
import ReportButton from './ReportButton.jsx'
import { Empty, ErrorMessage, FieldError, Loading } from './Status.jsx'

function Comments({ documentId }) {
  const { user } = useAuth()
  const location = useLocation()
  const [comments, setComments] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [body, setBody] = useState('')
  const [formError, setFormError] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    api(`/documents/${documentId}/comments?page=${page}`)
      .then((data) => {
        if (!active) return
        setCount(data.count)
        setHasMore(Boolean(data.next))
        // A comment added here may also arrive in a later page, so skip repeats.
        setComments((current) => {
          const known = current.map((comment) => comment.id)
          return [...current, ...data.results.filter((c) => !known.includes(c.id))]
        })
      })
      .catch((err) => active && setError(err))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [documentId, page])

  async function submit(event) {
    event.preventDefault()
    setFormError(null)
    try {
      const comment = await api(`/documents/${documentId}/comments`, {
        method: 'POST',
        body: { body },
      })
      setComments((current) => [...current, comment])
      setCount((current) => current + 1)
      setBody('')
    } catch (err) {
      setFormError(err.message)
    }
  }

  return (
    <section className="comments" aria-label="Comments">
      <h2>Comments ({count})</h2>

      {user ? (
        <form onSubmit={submit}>
          <label>
            Add a comment
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows="3"
              maxLength="2000"
              required
            />
          </label>
          <button type="submit">Post comment</button>
          <FieldError messages={formError} />
        </form>
      ) : (
        <p>
          <Link to="/login" state={{ from: location.pathname }}>
            Log in
          </Link>{' '}
          to join the conversation.
        </p>
      )}

      {error && <ErrorMessage error={error} />}
      {!error && !loading && comments.length === 0 && <Empty>No comments yet.</Empty>}

      <ul className="comment-list">
        {comments.map((comment) => (
          <li key={comment.id}>
            <p className="meta">
              <strong>{comment.user}</strong> · {formatDate(comment.created_at)}
            </p>
            <p className="comment-body">{comment.body}</p>
            {user && <ReportButton commentId={comment.id} />}
          </li>
        ))}
      </ul>

      {loading && <Loading />}
      {hasMore && !loading && (
        <button type="button" onClick={() => setPage(page + 1)}>
          Show more comments
        </button>
      )}
    </section>
  )
}

export default Comments
