import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { FieldError } from '../components/Status.jsx'

const EMPTY_FORM = { username: '', email: '', display_name: '', password: '', confirm: '' }

function Register() {
  const { user, setUser } = useAuth()
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  if (user) return <Navigate to="/" replace />

  function change(event) {
    setForm({ ...form, [event.target.name]: event.target.value })
  }

  async function submit(event) {
    event.preventDefault()
    if (form.password !== form.confirm) {
      setErrors({ confirm: 'The passwords do not match.' })
      return
    }
    setErrors({})
    setSaving(true)
    const { confirm: _confirm, ...body } = form
    try {
      setUser(await api('/auth/register', { method: 'POST', body }))
    } catch (err) {
      const known = Object.keys(EMPTY_FORM).some((name) => err.data[name])
      setErrors(known ? err.data : { form: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h1>Create an account</h1>
      <FieldError messages={errors.form} />
      <label>
        Username
        <input
          name="username"
          value={form.username}
          onChange={change}
          autoComplete="username"
          required
        />
      </label>
      <FieldError messages={errors.username} />
      <label>
        Email (optional)
        <input
          type="email"
          name="email"
          value={form.email}
          onChange={change}
          autoComplete="email"
        />
      </label>
      <FieldError messages={errors.email} />
      <label>
        Display name (optional)
        <input name="display_name" value={form.display_name} onChange={change} />
      </label>
      <FieldError messages={errors.display_name} />
      <label>
        Password
        <input
          type="password"
          name="password"
          value={form.password}
          onChange={change}
          autoComplete="new-password"
          required
        />
      </label>
      <FieldError messages={errors.password} />
      <label>
        Confirm password
        <input
          type="password"
          name="confirm"
          value={form.confirm}
          onChange={change}
          autoComplete="new-password"
          required
        />
      </label>
      <FieldError messages={errors.confirm} />
      <button type="submit" disabled={saving}>
        {saving ? 'Creating account...' : 'Create account'}
      </button>
      <p>
        Already registered? <Link to="/login">Log in</Link>
      </p>
    </form>
  )
}

export default Register
