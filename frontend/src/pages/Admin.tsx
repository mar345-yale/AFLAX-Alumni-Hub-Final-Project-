import { useCallback, useEffect, useState } from 'react'
import { api, rankAbbr } from '../api'
import type { AdminAccount } from '../api'
import { useAuth } from '../useAuth'
import Avatar from '../components/Avatar'
import UsagePanel from '../components/UsagePanel'

type Tab = 'pending' | 'approved' | 'rejected' | 'usage'

function describe(a: AdminAccount): string {
  if (a.status === 'Cadet') return 'Cadet'
  if (a.status === 'Civilian') return [a.job, a.city].filter(Boolean).join(' · ') || 'Civilian'
  return [a.rank && (rankAbbr[a.rank] ?? a.rank), a.afsc, a.aircraft, a.job, a.base].filter(Boolean).join(' · ')
}

export default function Admin() {
  const { user } = useAuth()
  const [accounts, setAccounts] = useState<AdminAccount[]>([])
  const [tab, setTab] = useState<Tab>('pending')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.accounts().then((r) => setAccounts(r.accounts)).catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  async function act(fn: () => Promise<unknown>) {
    setError('')
    try {
      await fn()
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed.')
    }
  }

  const counts = {
    pending: accounts.filter((a) => a.approval === 'pending').length,
    approved: accounts.filter((a) => a.approval === 'approved').length,
    rejected: accounts.filter((a) => a.approval === 'rejected').length,
  }
  const shown = accounts.filter((a) => a.approval === tab)

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">Alumni Board</p>
        <h1>Board tools</h1>
        <p className="muted">
          Review every new account before it can see member information, and keep an eye on Falcon Mentor's usage. Board
          members can also add games and tailgates from the Home page.
        </p>
      </header>

      <div className="tabs" role="tablist">
        {(['pending', 'approved', 'rejected'] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)} <span className="count-chip">{counts[t]}</span>
          </button>
        ))}
        <button role="tab" aria-selected={tab === 'usage'} className={`tab-right ${tab === 'usage' ? 'active' : ''}`} onClick={() => setTab('usage')}>
          Falcon Mentor usage
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {tab === 'usage' ? <UsagePanel /> : <div className="account-list">
        {shown.length === 0 && (
          <div className="card empty">{tab === 'pending' ? 'No accounts waiting for approval. 🎉' : `No ${tab} accounts.`}</div>
        )}
        {shown.map((a) => (
          <article key={a.id} className="card account">
            <Avatar first={a.first_name} last={a.last_name} photo={a.photo_url} size={52} />
            <div className="account-info">
              <strong>
                {a.first_name} {a.last_name}
                {a.role === 'admin' && <span className="badge badge-board">Board</span>}
              </strong>
              <span className="muted">Class of {a.grad_year} · {a.status}</span>
              <span>{describe(a)}</span>
              <span className="muted small">
                <a href={`mailto:${a.email}`}>{a.email}</a>{a.phone && ` · ${a.phone}`} · requested {new Date(`${a.created_at.replace(' ', 'T')}Z`).toLocaleDateString()}
              </span>
            </div>
            <div className="account-actions">
              {a.approval !== 'approved' && (
                <button className="btn btn-primary btn-sm" onClick={() => act(() => api.approve(a.id))}>Approve</button>
              )}
              {a.approval !== 'rejected' && a.id !== user?.id && (
                <button className="btn btn-danger btn-sm" onClick={() => act(() => api.reject(a.id))}>
                  {a.approval === 'approved' ? 'Revoke access' : 'Reject'}
                </button>
              )}
              {a.approval === 'approved' && a.id !== user?.id && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => act(() => api.setRole(a.id, a.role === 'admin' ? 'member' : 'admin'))}
                >
                  {a.role === 'admin' ? 'Remove from board' : 'Make board member'}
                </button>
              )}
            </div>
          </article>
        ))}
      </div>}
    </div>
  )
}
