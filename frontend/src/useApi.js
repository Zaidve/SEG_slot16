import { useEffect, useState } from 'react'
import { api } from './api'

// Load data from the API whenever path changes. Pass null to load nothing.
export function useApi(path) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(Boolean(path))
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!path) return undefined
    // Ignore a slow response if the page has already moved on.
    let active = true
    setLoading(true)
    setError(null)
    api(path)
      .then((result) => active && setData(result))
      .catch((err) => active && setError(err))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [path])

  return { data, setData, loading, error }
}
