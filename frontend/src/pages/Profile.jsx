import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { FieldError, Loading } from '../components/Status.jsx'

function Profile() {
  const { user, setUser, loading } = useAuth()
  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [avatar, setAvatar] = useState(null)
  const [errors, setErrors] = useState({})
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name)
      setBio(user.bio)
    }
  }, [user])

  if (loading) return <Loading />
  if (!user) return <Navigate to="/login" state={{ from: '/profile' }} replace />

  async function submit(event) {
    event.preventDefault()
    setErrors({})
    setSaved(false)
    setSaving(true)
    const body = new FormData()
    body.append('display_name', displayName)
    body.append('bio', bio)
    if (avatar) body.append('avatar', avatar)
    try {
      setUser(await api('/profile', { method: 'PATCH', body }))
      setAvatar(null)
      setSaved(true)
    } catch (err) {
      const known = err.data.display_name || err.data.bio || err.data.avatar
      setErrors(known ? err.data : { form: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h1>Your profile</h1>
      <p className="meta">
        Signed in as {user.username}
        {user.email && ` (${user.email})`}
      </p>
      {user.avatar && <img className="avatar" src={user.avatar} alt="Your avatar" />}
      <FieldError messages={errors.form} />
      <label>
        Display name
        <input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength="150"
        />
      </label>
      <FieldError messages={errors.display_name} />
      <label>
        Bio
        <textarea value={bio} onChange={(event) => setBio(event.target.value)} rows="4" />
      </label>
      <FieldError messages={errors.bio} />
      <label>
        Avatar
        <input
          key={user.avatar}
          type="file"
          accept="image/*"
          onChange={(event) => setAvatar(event.target.files[0] || null)}
        />
      </label>
      <FieldError messages={errors.avatar} />
      <button type="submit" disabled={saving}>
        {saving ? 'Saving...' : 'Save changes'}
      </button>
      {saved && (
        <p className="meta" role="status">
          Your profile has been saved.
        </p>
      )}
    </form>
  )
}

export default Profile
