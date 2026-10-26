import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Options } from '../api'
import PhotoPicker from '../components/PhotoPicker'
import ProfileFields from '../components/ProfileFields'
import { appendProfile, emptyProfile } from '../profileForm'
import type { ProfileValues } from '../profileForm'
import AuthLayout from './AuthLayout'

export default function Signup() {
  const navigate = useNavigate()
  const [options, setOptions] = useState<Options | null>(null)
  const [account, setAccount] = useState({ email: '', confirm_email: '', password: '', confirm_password: '' })
  const [profile, setProfile] = useState<ProfileValues>(emptyProfile)
  const [photo, setPhoto] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.options().then(setOptions).catch((e: Error) => setError(e.message))
  }, [])

  const emailMismatch = account.confirm_email !== '' && account.email.trim().toLowerCase() !== account.confirm_email.trim().toLowerCase()
  const passwordMismatch = account.confirm_password !== '' && account.password !== account.confirm_password
  const passwordShort = account.password !== '' && account.password.length < 8

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (emailMismatch || passwordMismatch || passwordShort) {
      setError('Please fix the highlighted fields.')
      return
    }
    setError('')
    setBusy(true)
    const form = new FormData()
    Object.entries(account).forEach(([k, v]) => form.append(k, v))
    appendProfile(form, profile)
    if (photo) form.append('photo', photo)
    try {
      await api.signup(form)
      navigate('/login', { replace: true, state: { signedUp: true } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign up failed.')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      wide
      title="Request an account"
      subtitle="Every account is reviewed by the AFLAX alumni board to protect our members' information."
    >
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {!options ? (
        <p className="muted">Loading form…</p>
      ) : (
        <form className="form" onSubmit={submit}>
          <h3 className="form-section">Account</h3>
          <div className="form-row">
            <label>
              Email (your username)
              <input type="email" required autoComplete="email" value={account.email}
                onChange={(e) => setAccount({ ...account, email: e.target.value })} />
            </label>
            <label className={emailMismatch ? 'invalid' : ''}>
              Confirm email
              <input type="email" required value={account.confirm_email}
                onChange={(e) => setAccount({ ...account, confirm_email: e.target.value })} />
              {emailMismatch && <small className="field-error">Emails don't match</small>}
            </label>
          </div>
          <div className="form-row">
            <label className={passwordShort ? 'invalid' : ''}>
              Password
              <input type="password" required autoComplete="new-password" value={account.password}
                onChange={(e) => setAccount({ ...account, password: e.target.value })} />
              {passwordShort && <small className="field-error">At least 8 characters</small>}
            </label>
            <label className={passwordMismatch ? 'invalid' : ''}>
              Confirm password
              <input type="password" required autoComplete="new-password" value={account.confirm_password}
                onChange={(e) => setAccount({ ...account, confirm_password: e.target.value })} />
              {passwordMismatch && <small className="field-error">Passwords don't match</small>}
            </label>
          </div>

          <h3 className="form-section">Profile</h3>
          <PhotoPicker first={profile.first_name} last={profile.last_name} current={null} file={photo} onFile={setPhoto} />
          <ProfileFields values={profile} options={options} onChange={(p) => setProfile({ ...profile, ...p })} />

          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Submitting…' : 'Submit for board approval'}
          </button>
        </form>
      )}
      <p className="auth-switch">Already approved? <Link to="/login">Log in</Link></p>
    </AuthLayout>
  )
}
