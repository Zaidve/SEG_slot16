import { useSearchParams } from 'react-router-dom'
import DocumentCard from '../components/DocumentCard.jsx'
import Pagination from '../components/Pagination.jsx'
import { Empty, ErrorMessage, Loading } from '../components/Status.jsx'
import { useApi } from '../useApi'

function Home() {
  const [params] = useSearchParams()
  const page = params.get('page') || 1
  const { data, loading, error } = useApi(`/documents?page=${page}`)

  return (
    <>
      <h1>Latest news</h1>
      {loading && <Loading />}
      {!loading && error && <ErrorMessage error={error} />}
      {!loading && !error && data && (
        <>
          {data.results.length === 0 && <Empty>No articles have been published yet.</Empty>}
          <div className="card-grid">
            {data.results.map((document) => (
              <DocumentCard key={document.id} document={document} />
            ))}
          </div>
          <Pagination count={data.count} />
        </>
      )}
    </>
  )
}

export default Home
