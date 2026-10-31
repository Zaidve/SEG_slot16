import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { FieldError } from '../components/Status.jsx'

function Login() {
  const { user, setUser } = useAuth()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  if (user) return <Navigate to={location.state?.from || '/'} replace />

  async function submit(event) {
    event.preventDefault()
    setErrors({})
    setSaving(true)
    try {
      setUser(await api('/auth/login', { method: 'POST', body: { username, password } }))
    } catch (err) {
      setErrors(err.data.username || err.data.password ? err.data : { form: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h1>Log in</h1>
      <FieldError messages={errors.form} />
      <label>
        Username
        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
        />
      </label>
      <FieldError messages={errors.username} />
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />
      </label>
      <FieldError messages={errors.password} />
      <button type="submit" disabled={saving}>
        {saving ? 'Logging in...' : 'Log in'}
      </button>
      <p>
        New here? <Link to="/register">Create an account</Link>
      </p>
    </form>
  )
}

export default Login
