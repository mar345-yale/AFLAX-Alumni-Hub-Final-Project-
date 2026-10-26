import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { Member, Options } from '../api'
import { useAuth } from '../useAuth'
import PhotoPicker from '../components/PhotoPicker'
import ProfileFields from '../components/ProfileFields'
import { appendProfile } from '../profileForm'
import type { ProfileValues } from '../profileForm'

function toValues(u: Member): ProfileValues {
  return {
    first_name: u.first_name, last_name: u.last_name, grad_year: String(u.grad_year), status: u.status,
    rank: u.rank ?? '', afsc: u.afsc ?? '', aircraft: u.aircraft ?? '', job: u.job ?? '', base: u.base ?? '',
    city: u.city ?? '', phone: u.phone ?? '', willing_to_mentor: u.willing_to_mentor, show_phone: u.show_phone,
  }
}

export default function Profile() {
  const { user, setUser } = useAuth()
  const [options, setOptions] = useState<Options | null>(null)
  const [values, setValues] = useState<ProfileValues | null>(user ? toValues(user) : null)
  const [photo, setPhoto] = useState<File | null>(null)
  const [msg, setMsg] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' })
  const [pwMsg, setPwMsg] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    api.options().then(setOptions).catch((e: Error) => setMsg({ kind: 'error', text: e.message }))
  }, [])

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!values) return
    setBusy(true)
    setMsg(null)
    const form = new FormData()
    appendProfile(form, values)
    if (photo) form.append('photo', photo)
    try {
      const updated = await api.updateMe(form)
      setUser(updated)
      setValues(toValues(updated))
      setPhoto(null)
      setMsg({ kind: 'success', text: 'Profile saved.' })
    } catch (err) {
      setMsg({ kind: 'error', text: err instanceof Error ? err.message : 'Could not save.' })
    } finally {
      setBusy(false)
    }
  }

  async function changePassword(e: FormEvent) {
    e.preventDefault()
    if (pw.next !== pw.confirm) {
      setPwMsg({ kind: 'error', text: "New passwords don't match." })
      return
    }
    try {
      await api.changePassword(pw.current, pw.next)
      setPw({ current: '', next: '', confirm: '' })
      setPwMsg({ kind: 'success', text: 'Password updated.' })
    } catch (err) {
      setPwMsg({ kind: 'error', text: err instanceof Error ? err.message : 'Could not update password.' })
    }
  }

  if (!user || !values) return null
  return (
    <div className="page narrow">
      <header className="page-head">
        <p className="eyebrow">My profile</p>
        <h1>{user.first_name} {user.last_name}</h1>
        <p className="muted">{user.email} · Class of {user.grad_year}{user.role === 'admin' && ' · Alumni Board'}</p>
      </header>

      <form className="card form" onSubmit={save}>
        <h3 className="form-section">Profile details</h3>
        <PhotoPicker first={values.first_name} last={values.last_name} current={user.photo_url} file={photo} onFile={setPhoto} />
        {options ? (
          <ProfileFields values={values} options={options} onChange={(p) => setValues({ ...values, ...p })} />
        ) : (
          <p className="muted">Loading…</p>
        )}
        {msg && <div className={`alert alert-${msg.kind}`}>{msg.text}</div>}
        <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save profile'}</button>
      </form>

      <form className="card form" onSubmit={changePassword}>
        <h3 className="form-section">Change password</h3>
        <div className="form-row">
          <label>Current password<input type="password" required autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
        </div>
        <div className="form-row">
          <label>New password<input type="password" required minLength={8} autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
          <label>Confirm new password<input type="password" required minLength={8} autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></label>
        </div>
        {pwMsg && <div className={`alert alert-${pwMsg.kind}`}>{pwMsg.text}</div>}
        <button className="btn btn-outline">Update password</button>
      </form>
    </div>
  )
}
