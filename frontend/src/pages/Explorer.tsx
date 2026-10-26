import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, rankAbbr } from '../api'
import type { AfscDetail, BaseDetail, ExploreAfsc, ExploreAlumnus, ExploreBase } from '../api'
import Avatar from '../components/Avatar'

type Tab = 'afscs' | 'bases'

function AlumniList({ alumni }: { alumni: ExploreAlumnus[] }) {
  if (!alumni.length) return <p className="muted">No AFLAX alumni here yet.</p>
  return (
    <ul className="explore-alumni">
      {alumni.map((a) => (
        <li key={a.id}>
          <Avatar first={a.first_name} last={a.last_name} photo={a.photo_url} size={36} />
          <div>
            <strong>{a.rank && a.status !== 'Civilian' ? `${rankAbbr[a.rank] ?? a.rank} ` : ''}{a.first_name} {a.last_name}</strong>
            <small className="muted">Class of {a.grad_year} · {a.job || a.afsc_title} · {a.location}</small>
          </div>
          <a className="btn btn-outline btn-sm" href={`mailto:${a.email}`}>Email</a>
        </li>
      ))}
    </ul>
  )
}

function AfscPanel({ code }: { code: string }) {
  const [d, setD] = useState<AfscDetail | null>(null)
  const [showOfficial, setShowOfficial] = useState(false)
  useEffect(() => {
    api.exploreAfsc(code).then(setD).catch(() => setD(null))
  }, [code])
  if (!d || d.code !== code) return <p className="muted">Loading…</p>
  return (
    <>
      <p className="eyebrow">{d.category} · {d.code}</p>
      <h2>{d.title}</h2>
      <p>{d.overview}</p>
      <dl className="explore-facts">
        <dt>Training</dt><dd>{d.training}</dd>
        <dt>Lifestyle</dt><dd>{d.lifestyle}</dd>
        <dt>Good fit if</dt><dd>{d.good_fit}</dd>
        <dt>Typical bases</dt><dd>{d.typical_bases.join(' · ')}</dd>
      </dl>
      <button className="link-btn" onClick={() => setShowOfficial((v) => !v)}>
        {showOfficial ? 'Hide' : 'Show'} official Air Force description
      </button>
      {showOfficial && <p className="official-text">{d.official_description}</p>}
      <h3 className="panel-subhead">AFLAX alumni in {d.code} ({d.alumni.length})</h3>
      <AlumniList alumni={d.alumni} />
      <Link className="btn btn-gold" to={`/mentorship?q=${encodeURIComponent(`Tell me what it's really like to be in ${d.title} (${d.code}) and who I should talk to.`)}`}>
        Ask Falcon Mentor about {d.title}
      </Link>
    </>
  )
}

function BasePanel({ name }: { name: string }) {
  const [d, setD] = useState<BaseDetail | null>(null)
  useEffect(() => {
    api.exploreBase(name).then(setD).catch(() => setD(null))
  }, [name])
  if (!d || d.name !== name) return <p className="muted">Loading…</p>
  return (
    <>
      <p className="eyebrow">{d.region} · {d.type}</p>
      <h2>{d.name}</h2>
      <dl className="explore-facts">
        <dt>Nearby</dt><dd>{d.nearby_city}</dd>
        <dt>Missions</dt><dd>{d.missions.join(' · ')}</dd>
        <dt>Aircraft</dt><dd>{d.aircraft.length ? d.aircraft.join(', ') : 'No assigned flying mission'}</dd>
        <dt>Cost of living</dt><dd>{d.cost_of_living}</dd>
      </dl>
      <div className="pros-cons">
        <div><h4>Pros</h4><ul>{d.pros.map((p) => <li key={p}>{p}</li>)}</ul></div>
        <div><h4>Cons</h4><ul>{d.cons.map((c) => <li key={c}>{c}</li>)}</ul></div>
      </div>
      <h3 className="panel-subhead">AFLAX alumni at {d.name.split(',')[0]} ({d.alumni.length})</h3>
      <AlumniList alumni={d.alumni} />
      <Link className="btn btn-gold" to={`/mentorship?q=${encodeURIComponent(`What is life like at ${d.name}, and which AFLAX alumni there could I talk to?`)}`}>
        Ask Falcon Mentor about {d.name.split(',')[0]}
      </Link>
    </>
  )
}

export default function Explorer() {
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'bases' ? 'bases' : 'afscs'
  const selected = params.get('item')
  const [afscs, setAfscs] = useState<ExploreAfsc[]>([])
  const [bases, setBases] = useState<ExploreBase[]>([])
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [region, setRegion] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.exploreAfscs(), api.exploreBases()])
      .then(([a, b]) => {
        setAfscs(a)
        setBases(b)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const q = query.trim().toLowerCase()
  const shownAfscs = useMemo(() => afscs.filter((a) =>
    (!category || a.category === category) &&
    (!q || [a.code, a.title, a.overview, ...a.keywords].join(' ').toLowerCase().includes(q))), [afscs, category, q])
  const regions = useMemo(() => [...new Set(bases.map((b) => b.region))].sort(), [bases])
  const shownBases = useMemo(() => bases.filter((b) =>
    (!region || b.region === region) &&
    (!q || [b.name, b.region, b.type, b.nearby_city, ...b.missions, ...b.aircraft].join(' ').toLowerCase().includes(q))), [bases, region, q])

  const open = (item: string | null) => {
    const next = new URLSearchParams(params)
    if (item) next.set('item', item)
    else next.delete('item')
    setParams(next)
  }
  const switchTab = (t: Tab) => {
    setQuery('')
    setParams(new URLSearchParams({ tab: t }))
  }

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">Explorer</p>
        <h1>Career fields &amp; bases</h1>
        <p className="muted">
          Browse every officer AFSC and Air Force installation, see which AFLAX alumni are there, and reach out directly.
          Want a personalized take? Ask Falcon Mentor from any page here.
        </p>
      </header>

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'afscs'} className={tab === 'afscs' ? 'active' : ''} onClick={() => switchTab('afscs')}>
          AFSCs <span className="count-chip">{afscs.length}</span>
        </button>
        <button role="tab" aria-selected={tab === 'bases'} className={tab === 'bases' ? 'active' : ''} onClick={() => switchTab('bases')}>
          Bases <span className="count-chip">{bases.length}</span>
        </button>
      </div>

      <div className="filter-bar card">
        <label>
          Search
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={tab === 'afscs' ? 'e.g. space, flying, engineering, 17D1' : 'e.g. Colorado, F-35, beach, Europe'}
          />
        </label>
        {tab === 'afscs' ? (
          <label>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>
              <option value="Rated">Rated (aircrew)</option>
              <option value="Nonrated">Nonrated</option>
            </select>
          </label>
        ) : (
          <label>
            Region
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">All regions</option>
              {regions.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className={`explore-layout ${selected ? 'with-panel' : ''}`}>
        <div className="explore-grid">
          {tab === 'afscs'
            ? shownAfscs.map((a) => (
                <button key={a.code} className={`explore-card card ${selected === a.code ? 'selected' : ''}`} onClick={() => open(a.code)}>
                  <span className="explore-card-top">
                    <span className={`badge ${a.category === 'Rated' ? 'badge-home' : 'badge-away'}`}>{a.code}</span>
                    {a.alumni_count > 0 && <span className="muted small">{a.alumni_count} alumni</span>}
                  </span>
                  <strong>{a.title}</strong>
                  <span className="muted small">{a.overview}</span>
                </button>
              ))
            : shownBases.map((b) => (
                <button key={b.name} className={`explore-card card ${selected === b.name ? 'selected' : ''}`} onClick={() => open(b.name)}>
                  <span className="explore-card-top">
                    <span className="badge badge-away">{b.region}</span>
                    {b.alumni_count > 0 && <span className="muted small">{b.alumni_count} alumni</span>}
                  </span>
                  <strong>{b.name}</strong>
                  <span className="muted small">{b.missions[0]}</span>
                </button>
              ))}
          {(tab === 'afscs' ? shownAfscs : shownBases).length === 0 && <p className="empty">Nothing matches that search.</p>}
        </div>

        {selected && (
          <aside className="explore-panel card">
            <button className="explore-close" aria-label="Close" onClick={() => open(null)}>×</button>
            {tab === 'afscs' ? <AfscPanel code={selected} /> : <BasePanel name={selected} />}
          </aside>
        )}
      </div>
    </div>
  )
}
