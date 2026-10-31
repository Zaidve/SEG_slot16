import { Link } from 'react-router-dom'
import { formatDate } from '../format'

function DocumentCard({ document, onOpen }) {
  return (
    <article className="card">
      {document.image && (
        <img src={document.image} alt={document.image_alt} loading="lazy" />
      )}
      <div className="card-body">
        <p className="meta">
          {document.category.name} · {formatDate(document.published_at)}
        </p>
        <h2>
          <Link to={`/documents/${document.slug}`} onClick={onOpen}>
            {document.title}
          </Link>
        </h2>
        <p>{document.summary}</p>
        <p className="meta">By {document.author}</p>
      </div>
    </article>
  )
}

export default DocumentCard
