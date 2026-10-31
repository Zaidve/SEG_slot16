import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, PAGE_SIZE } from '../api'
import DocumentCard from '../components/DocumentCard.jsx'
import Pagination from '../components/Pagination.jsx'
import { Empty, ErrorMessage, Loading } from '../components/Status.jsx'
import { plural } from '../format'
import { useApi } from '../useApi'

const FILTERS = ['q', 'category', 'tag', 'from', 'to']

function Search() {
  const [params, setParams] = useSearchParams()
  const { data: categories } = useApi('/categories')
  const { data: tags } = useApi('/tags')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const page = Number(params.get('page')) || 1
  const hasCriteria = FILTERS.some((name) => params.get(name))

  // What the visitor asked for. Adding query_id to the URL must not search again.
  const criteria = new URLSearchParams(params)
  criteria.delete('query_id')
  const searchKey = criteria.toString()

  useEffect(() => {
    if (!hasCriteria) {
      setData(null)
      return undefined
    }
    let active = true
    setLoading(true)
    setError(null)
    api(`/search?${params}`)
      .then((result) => {
        if (!active) return
        setData(result)
        // Keep query_id in the URL, so changing page or coming back from an
        // article continues this search instead of logging a new one.
        setParams(
          (current) => {
            const next = new URLSearchParams(current)
            next.set('query_id', result.query_id)
            return next
          },
          { replace: true },
        )
      })
      .catch((err) => active && setError(err))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [searchKey]) // only searchKey: see the comment above it

  function submit(event) {
    event.preventDefault()
    const next = new URLSearchParams()
    new FormData(event.target).forEach((value, name) => {
      if (value.trim()) next.set(name, value.trim())
    })
    setParams(next)
  }

  function recordClick(document, index) {
    // Position is the rank across all pages, starting at 1.
    const position = (page - 1) * PAGE_SIZE + index + 1
    api('/search/click', {
      method: 'POST',
      body: { query_id: data.query_id, document: document.id, position },
    }).catch(() => {}) // a lost click should never stop the reader
  }

  // Remount the form when the search changes or the filter options load,
  // so its default values always match the URL.
  const formKey = `${searchKey}-${categories?.length}-${tags?.length}`

  return (
    <>
      <h1>Search</h1>
      <form key={formKey} className="search-form" onSubmit={submit}>
        <label className="search-keyword">
          Keyword
          <input type="search" name="q" defaultValue={params.get('q') || ''} />
        </label>
        <label>
          Category
          <select name="category" defaultValue={params.get('category') || ''}>
            <option value="">All categories</option>
            {(categories || []).map((category) => (
              <option key={category.id} value={category.slug}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tag
          <select name="tag" defaultValue={params.get('tag') || ''}>
            <option value="">All tags</option>
            {(tags || []).map((tag) => (
              <option key={tag.id} value={tag.slug}>
                {tag.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="date" name="from" defaultValue={params.get('from') || ''} />
        </label>
        <label>
          To
          <input type="date" name="to" defaultValue={params.get('to') || ''} />
        </label>
        <button type="submit">Search</button>
      </form>

      {!hasCriteria && <Empty>Enter a keyword or choose a filter to start.</Empty>}
      {hasCriteria && loading && <Loading />}
      {hasCriteria && !loading && error && <ErrorMessage error={error} />}
      {hasCriteria && !loading && !error && data && (
        <>
          <p className="meta" role="status">
            {plural(data.count, 'result')}
          </p>
          {data.results.length === 0 && <Empty>No articles match your search.</Empty>}
          <div className="card-grid">
            {data.results.map((document, index) => (
              <DocumentCard
                key={document.id}
                document={document}
                onOpen={() => recordClick(document, index)}
              />
            ))}
          </div>
          <Pagination count={data.count} />
        </>
      )}
    </>
  )
}

export default Search
