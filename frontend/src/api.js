// Must match PAGE_SIZE in the Django REST_FRAMEWORK settings.
export const PAGE_SIZE = 10

export class ApiError extends Error {
  constructor(status, data) {
    super(firstMessage(data) || `Request failed (${status})`)
    this.status = status
    this.data = data || {}
  }
}

// DRF errors look like {detail: '...'} or {field: ['...']}.
function firstMessage(data) {
  if (!data || typeof data !== 'object') return null
  if (data.detail) return data.detail
  const first = Object.values(data)[0]
  return Array.isArray(first) ? first[0] : null
}

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? match[1] : null
}

async function csrfToken() {
  if (!getCookie('csrftoken')) await fetch('/api/auth/csrf')
  return getCookie('csrftoken')
}

// Every API call goes through here. Pass a plain object for JSON,
// or FormData for file uploads.
export async function api(path, { method = 'GET', body } = {}) {
  const options = { method, headers: {} }
  if (method !== 'GET') {
    options.headers['X-CSRFToken'] = await csrfToken()
  }
  if (body instanceof FormData) {
    options.body = body
  } else if (body) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  const response = await fetch(`/api${path}`, options)
  if (response.status === 204) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, data)
  return data
}
