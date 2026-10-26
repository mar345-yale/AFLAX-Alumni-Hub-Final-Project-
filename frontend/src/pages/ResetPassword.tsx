import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, session } from '../api'
import AuthLayout from './AuthLayout'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (password !== confirm) {
      setError("Passwords don't match.")
      return
    }
    setError('')
    setBusy(true)
    try {
      setDone((await api.resetPassword(token, password)).message)
      session.clear() // the reset signs out every device, including this one
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Set a new password" subtitle="Choose a password with at least 8 characters.">
      {!token ? (
        <div className="alert alert-error">This link is missing its reset code. Request a new link.</div>
      ) : done ? (
        <div className="alert alert-success">{done}</div>
      ) : (
        <form className="form" onSubmit={submit}>
          <label>
            New password
            <input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <label>
            Confirm new password
            <input type="password" required minLength={8} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </label>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <button className="btn btn-primary btn-block" disabled={busy}>{busy ? 'Saving…' : 'Update password'}</button>
        </form>
      )}
      <p className="auth-switch">
        {done ? <a href="/login">Go to log in</a> : <><Link to="/forgot-password">Request a new link</Link> · <Link to="/login">Log in</Link></>}
      </p>
    </AuthLayout>
  )
}
