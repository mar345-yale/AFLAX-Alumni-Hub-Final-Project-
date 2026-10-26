import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../useAuth'
import AuthLayout from './AuthLayout'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const justSignedUp = (location.state as { signedUp?: boolean } | null)?.signedUp
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Welcome back, Falcon" subtitle="Log in to the AFLAX alumni and cadet portal.">
      {justSignedUp && (
        <div className="alert alert-success">
          Thanks for signing up! The AFLAX alumni board will review your account. You can log in once it's approved.
        </div>
      )}
      <form className="form" onSubmit={submit}>
        <label>
          Email
          <input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          <span className="label-row">
            Password
            <Link to="/forgot-password" className="small">Forgot password?</Link>
          </span>
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
      </form>
      <p className="auth-switch">New to the portal? <Link to="/signup">Request an account</Link></p>
    </AuthLayout>
  )
}
