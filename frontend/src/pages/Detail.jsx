import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import Comments from '../components/Comments.jsx'
import { ErrorMessage, FieldError, Loading } from '../components/Status.jsx'
import TagForm from '../components/TagForm.jsx'
import { formatDate, plural } from '../format'
import { useApi } from '../useApi'

function TagLinks({ tags }) {
  return tags.map((tag) => (
    <Link key={tag.id} to={`/search?tag=${tag.slug}`} className="tag">
      {tag.name}
    </Link>
  ))
}

function Detail() {
  const { slug } = useParams()
  const { user } = useAuth()
  const location = useLocation()
  const { data: document, setData, loading, error } = useApi(`/documents/${slug}`)
  const [likeError, setLikeError] = useState(null)

  const title = document?.seo_title || document?.title
  useEffect(() => {
    if (!title) return undefined
    const previous = window.document.title
    window.document.title = title
    return () => {
      window.document.title = previous
    }
  }, [title])

  if (loading) return <Loading />
  if (error) return <ErrorMessage error={error} />
  if (!document) return null

  async function toggleLike() {
    setLikeError(null)
    try {
      const result = await api(`/documents/${document.id}/like`, { method: 'POST' })
      setData({ ...document, ...result })
    } catch (err) {
      setLikeError(err.message)
    }
  }

  function addUserTag(tag) {
    setData({ ...document, user_tags: [...document.user_tags, tag] })
  }

  return (
    <article className="article">
      {document.seo_description && (
        <meta name="description" content={document.seo_description} />
      )}
      {document.seo_keywords && <meta name="keywords" content={document.seo_keywords} />}

      <p className="meta">
        <Link to={`/search?category=${document.category.slug}`}>{document.category.name}</Link>
      </p>
      <h1>{document.title}</h1>
      <p className="meta">
        By {document.author} · {formatDate(document.published_at)} ·{' '}
        {plural(document.views_count, 'view')}
      </p>
      {document.image && <img src={document.image} alt={document.image_alt} />}

      {/* Safe to render: Document.save() sanitizes content with nh3 on the server. */}
      <div className="article-body" dangerouslySetInnerHTML={{ __html: document.content }} />

      {document.tags.length > 0 && (
        <p className="tag-row">
          <span className="meta">Tags</span> <TagLinks tags={document.tags} />
        </p>
      )}
      {document.user_tags.length > 0 && (
        <p className="tag-row">
          <span className="meta">Reader tags</span> <TagLinks tags={document.user_tags} />
        </p>
      )}

      {user ? (
        <div className="article-actions">
          <button
            type="button"
            className={document.liked ? 'liked' : undefined}
            aria-pressed={document.liked}
            onClick={toggleLike}
          >
            {document.liked ? 'Liked' : 'Like'} ({document.like_count})
          </button>
          <FieldError messages={likeError} />
          <TagForm
            documentId={document.id}
            userTags={document.user_tags}
            onAdded={addUserTag}
          />
        </div>
      ) : (
        <p>
          {plural(document.like_count, 'like')}.{' '}
          <Link to="/login" state={{ from: location.pathname }}>
            Log in
          </Link>{' '}
          to like or tag this article.
        </p>
      )}

      <Comments documentId={document.id} />
    </article>
  )
}

export default Detail
