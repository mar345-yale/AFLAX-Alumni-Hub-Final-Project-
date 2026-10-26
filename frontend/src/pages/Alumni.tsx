import { useEffect, useState } from 'react'
import { MapContainer, Marker, TileLayer, Tooltip } from 'react-leaflet'
import { api, rankAbbr } from '../api'
import type { AlumniResult } from '../api'
import Avatar from '../components/Avatar'
import { FitBounds } from '../components/mapUtils'
import { TILE_ATTRIBUTION, TILE_URL, countIcon } from '../mapIcons'

interface Filters { status: string; base: string; afsc: string; location: string }
const NO_FILTERS: Filters = { status: '', base: '', afsc: '', location: '' }

export default function Alumni() {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  // Results are tagged with the filters that produced them, so "loading" is derived:
  // it's true whenever the latest results don't match the current filters yet.
  const [result, setResult] = useState<{ key: string; data: AlumniResult } | null>(null)
  const [error, setError] = useState('')
  const key = JSON.stringify(filters)
  const data = result?.data ?? null
  const loading = result?.key !== key && !error

  useEffect(() => {
    let cancelled = false
    api.alumni(JSON.parse(key) as Record<string, string>)
      .then((d) => !cancelled && setResult({ key, data: d }))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [key])

  // Changing a dropdown resets the clicked-pin location.
  const setFilter = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, location: '', ...patch }))
  const anyFilter = Object.values(filters).some(Boolean)
  const points: [number, number][] = (data?.pins ?? []).map((p) => [p.lat, p.lng])

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">Alumni Connection</p>
        <h1>Who's where</h1>
        <p className="muted">
          Find AFLAX teammates by status, base, or career field. Click a blue marker to see everyone at that location.
        </p>
      </header>

      <div className="filter-bar card">
        <label>
          Military status
          <select value={filters.status} onChange={(e) => setFilter({ status: e.target.value })}>
            <option value="">All statuses</option>
            {data?.facets.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label>
          Base
          <select value={filters.base} onChange={(e) => setFilter({ base: e.target.value })}>
            <option value="">All bases</option>
            {data?.facets.bases.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
        <label>
          AFSC
          <select value={filters.afsc} onChange={(e) => setFilter({ afsc: e.target.value })}>
            <option value="">All AFSCs</option>
            {data?.facets.afscs.map(([code, title]) => (
              <option key={code} value={code}>{code} · {title ?? ''}</option>
            ))}
          </select>
        </label>
        <button className="btn btn-ghost btn-sm" disabled={!anyFilter} onClick={() => setFilters(NO_FILTERS)}>
          Clear filters
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card map-card">
        <MapContainer center={[30, -40]} zoom={2} minZoom={2} worldCopyJump className="map map-tall">
          <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} />
          <FitBounds points={points} maxZoom={7} />
          {data?.pins.map((p) => (
            <Marker
              key={p.label}
              position={[p.lat, p.lng]}
              icon={countIcon(p.count, filters.location === p.label)}
              zIndexOffset={filters.location === p.label ? 1000 : p.count}
              eventHandlers={{ click: () => setFilters((f) => ({ ...f, location: f.location === p.label ? '' : p.label })) }}
            >
              <Tooltip direction="top" offset={[0, -18]}>
                {p.label}: {p.count} {p.count === 1 ? 'member' : 'members'}
              </Tooltip>
            </Marker>
          ))}
        </MapContainer>
        {data && data.pins.length === 0 && !loading && <div className="map-empty">No members match these filters.</div>}
      </div>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>
              Roster{' '}
              <span className="count-chip">{data?.roster.length ?? 0}</span>
            </h2>
            {filters.location && (
              <p className="location-chip">
                Showing members at <strong>{filters.location}</strong>
                <button className="link-btn" onClick={() => setFilters((f) => ({ ...f, location: '' }))}>Show all locations</button>
              </p>
            )}
            {!filters.location && data && data.unmapped > 0 && (
              <p className="muted small">{data.unmapped} member{data.unmapped === 1 ? '' : 's'} without a mapped location still appear below.</p>
            )}
          </div>
        </div>

        <div className="table-wrap card">
          <table className="roster">
            <thead>
              <tr>
                <th>Name</th>
                <th>Class</th>
                <th>Rank</th>
                <th>AFSC</th>
                <th>Job</th>
                <th>Location</th>
                <th>Phone</th>
                <th>Email</th>
              </tr>
            </thead>
            <tbody>
              {data?.roster.map((m) => (
                <tr key={m.id}>
                  <td data-label="Name">
                    <span className="roster-name">
                      <Avatar first={m.first_name} last={m.last_name} photo={m.photo_url} size={34} />
                      <span>
                        <strong>{m.last_name}, {m.first_name}</strong>
                        <small className={`status-tag status-${m.status.replace(/\W/g, '').toLowerCase()}`}>{m.status}</small>
                      </span>
                    </span>
                  </td>
                  <td data-label="Class">{m.grad_year}</td>
                  <td data-label="Rank">{m.rank ? <span title={m.rank}>{rankAbbr[m.rank] ?? m.rank}</span> : '—'}</td>
                  <td data-label="AFSC">{m.afsc ? <span title={m.afsc_title ?? ''}>{m.afsc}</span> : '—'}{m.aircraft && <small className="muted"> · {m.aircraft}</small>}</td>
                  <td data-label="Job">{m.job || '—'}</td>
                  <td data-label="Location">{m.location || '—'}</td>
                  <td data-label="Phone">
                    {m.phone ? <a href={`tel:${m.phone.replace(/[^\d+]/g, '')}`}>{m.phone}</a> : m.phone_hidden ? <span className="muted small">Hidden</span> : '—'}
                    {m.phone && m.phone_hidden && <small className="muted" title="Hidden from members; visible to you"> 🔒</small>}
                  </td>
                  <td data-label="Email"><a href={`mailto:${m.email}`}>{m.email}</a></td>
                </tr>
              ))}
              {data && data.roster.length === 0 && (
                <tr><td colSpan={8} className="empty">No members match these filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
