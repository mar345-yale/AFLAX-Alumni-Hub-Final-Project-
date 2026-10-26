import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Usage, UsageTotals } from '../api'

const fmt = (n: number) => n.toLocaleString()

function cacheRate(t: UsageTotals): string {
  return t.input_tokens ? `${Math.round((t.cache_read_tokens / t.input_tokens) * 100)}%` : '—'
}

function perMessage(t: UsageTotals): string {
  return t.messages ? fmt(Math.round((t.input_tokens + t.output_tokens) / t.messages)) : '—'
}

/** Falcon Mentor token usage for the board: volume, cache hit rate, cost, heaviest users. */
export default function UsagePanel() {
  const [usage, setUsage] = useState<Usage | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.usage().then(setUsage).catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <div className="alert alert-error">{error}</div>
  if (!usage) return <p className="muted">Loading usage…</p>

  const windows: [string, UsageTotals][] = [
    ['Today', usage.totals.today], ['Last 7 days', usage.totals['7d']], ['Last 30 days', usage.totals['30d']],
  ]
  return (
    <div className="usage">
      <div className="usage-grid">
        {windows.map(([label, t]) => (
          <article key={label} className="card usage-card">
            <h4>{label}</h4>
            <p className="usage-big">{fmt(t.messages)} <small>messages</small></p>
            <dl>
              <dt>Model calls</dt><dd>{fmt(t.requests)} <small className="muted">({fmt(t.tool_calls)} tool calls)</small></dd>
              <dt>Input tokens</dt><dd>{fmt(t.input_tokens)}</dd>
              <dt>Cached input</dt><dd>{fmt(t.cache_read_tokens)} <small className="muted">({cacheRate(t)})</small></dd>
              <dt>Output tokens</dt><dd>{fmt(t.output_tokens)} <small className="muted">({fmt(t.reasoning_tokens)} reasoning)</small></dd>
              <dt>Tokens / message</dt><dd>{perMessage(t)}</dd>
              <dt>Avg response</dt><dd>{t.messages ? `${(t.avg_ms / 1000).toFixed(1)} s` : '—'}</dd>
              <dt>Est. cost</dt><dd>{t.est_cost_usd != null ? `$${t.est_cost_usd.toFixed(2)}` : <small className="muted">set prices in .env</small>}</dd>
              {t.errors > 0 && <><dt>Errors</dt><dd className="loss">{t.errors}</dd></>}
            </dl>
          </article>
        ))}
      </div>

      <div className="usage-tables">
        <div className="card">
          <h4>Top members (30 days)</h4>
          {usage.top_users.length === 0 ? <p className="muted">No chats yet.</p> : (
            <table className="mini-table">
              <thead><tr><th>Member</th><th>Messages</th><th>Tokens</th></tr></thead>
              <tbody>{usage.top_users.map((u) => (
                <tr key={u.name}><td>{u.name}</td><td>{u.messages}</td><td>{fmt(u.tokens)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h4>Recent messages</h4>
          {usage.recent.length === 0 ? <p className="muted">No chats yet.</p> : (
            <table className="mini-table">
              <thead><tr><th>When (UTC)</th><th>Member</th><th>Calls</th><th>In / cached / out</th><th>Time</th></tr></thead>
              <tbody>{usage.recent.map((r, i) => (
                <tr key={i} className={r.status === 'error' ? 'loss' : ''}>
                  <td>{r.created_at.slice(5, 16)}</td><td>{r.name}</td><td>{r.requests}</td>
                  <td>{fmt(r.input_tokens)} / {fmt(r.cache_read_tokens)} / {fmt(r.output_tokens)}</td>
                  <td>{(r.duration_ms / 1000).toFixed(1)}s</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </div>
      <p className="muted small">Each member can send {usage.daily_limit} Falcon Mentor messages per day (CHAT_DAILY_LIMIT).</p>
    </div>
  )
}
