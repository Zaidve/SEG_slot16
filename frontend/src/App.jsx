import { useEffect, useState } from 'react'

function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then(async (response) => {
        // A 503 still has a JSON body saying what is wrong, so show it.
        const body = await response.json().catch(() => null)
        if (!body) throw new Error(`HTTP ${response.status}`)
        return body
      })
      .then(setHealth)
      .catch((err) => setError(err.message))
  }, [])

  return (
    <main>
      <h1>News Portal</h1>
      {error && <p>Could not reach the API: {error}</p>}
      {!error && !health && <p>Checking the API...</p>}
      {health && (
        <p>
          API status: {health.status}, database: {health.database}
        </p>
      )}
    </main>
  )
}

export default App
