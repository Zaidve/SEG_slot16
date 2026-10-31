import { Link, useSearchParams } from 'react-router-dom'
import { PAGE_SIZE } from '../api'

function Pagination({ count }) {
  const [params] = useSearchParams()
  const page = Number(params.get('page')) || 1
  const totalPages = Math.ceil(count / PAGE_SIZE)
  if (totalPages <= 1) return null

  function linkTo(number) {
    const next = new URLSearchParams(params)
    next.set('page', number)
    return `?${next}`
  }

  return (
    <nav className="pagination" aria-label="Pages">
      {page > 1 ? <Link to={linkTo(page - 1)}>Previous</Link> : <span />}
      <span>
        Page {page} of {totalPages}
      </span>
      {page < totalPages ? <Link to={linkTo(page + 1)}>Next</Link> : <span />}
    </nav>
  )
}

export default Pagination
