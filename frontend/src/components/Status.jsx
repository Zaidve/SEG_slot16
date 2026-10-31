export function Loading() {
  return (
    <p className="status" role="status">
      Loading...
    </p>
  )
}

export function Empty({ children }) {
  return <p className="status">{children}</p>
}

export function ErrorMessage({ error }) {
  let message = error.message
  if (error.status === 404) message = 'Sorry, we could not find that page.'
  if (error.status >= 500) message = 'Something went wrong. Please try again soon.'
  return (
    <p className="status status-error" role="alert">
      {message}
    </p>
  )
}

export function FieldError({ messages }) {
  if (!messages) return null
  return (
    <p className="field-error" role="alert">
      {[].concat(messages).join(' ')}
    </p>
  )
}
