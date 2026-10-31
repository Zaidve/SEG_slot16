import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import { FieldError } from './Status.jsx'

function TagForm({ documentId, userTags, onAdded }) {
  const { data: tags } = useApi('/tags')
  const [slug, setSlug] = useState('')
  const [error, setError] = useState(null)

  const usedSlugs = userTags.map((tag) => tag.slug)
  const available = (tags || []).filter((tag) => !usedSlugs.includes(tag.slug))

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      const tag = await api(`/documents/${documentId}/tags`, {
        method: 'POST',
        body: { tag: slug },
      })
      onAdded(tag)
      setSlug('')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <label>
        Add a tag
        <select value={slug} onChange={(event) => setSlug(event.target.value)} required>
          <option value="">Choose a tag</option>
          {available.map((tag) => (
            <option key={tag.id} value={tag.slug}>
              {tag.name}
            </option>
          ))}
        </select>
      </label>
      <button type="submit">Add tag</button>
      <FieldError messages={error} />
    </form>
  )
}

export default TagForm
