import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { Game, Schedule, ScheduledTailgate, Tailgate } from '../api'
import { addGameToCalendar, addTailgateToCalendar } from '../calendar'
import { useAuth } from '../useAuth'
import { FitBounds, FlyTo } from '../components/mapUtils'
import { TILE_ATTRIBUTION, TILE_URL, milesBetween, venueIcon, youIcon } from '../mapIcons'

const fmtDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }).toUpperCase()

interface Venue {
  key: string
  lat: number
  lng: number
  games: Game[]
}

// One map pin per venue: games at the same coordinates (e.g. every USAFA home game) share it.
function groupByVenue(games: Game[]): Venue[] {
  const venues = new Map<string, Venue>()
  for (const g of games) {
    if (g.lat == null || g.lng == null) continue
    const key = `${g.lat.toFixed(3)},${g.lng.toFixed(3)}`
    const v = venues.get(key) ?? { key, lat: g.lat, lng: g.lng, games: [] }
    v.games.push(g)
    venues.set(key, v)
  }
  return [...venues.values()]
}

const isWin = (r: string) => r.startsWith('W')
const isLoss = (r: string) => r.startsWith('L')

function record(games: Game[]) {
  const w = games.filter((g) => isWin(g.result)).length
  const l = games.filter((g) => isLoss(g.result)).length
  return `${w}-${l}`
}

export default function Home() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [data, setData] = useState<Schedule | null>(null)
  const [error, setError] = useState('')
  const [season, setSeason] = useState<number | null>(null)
  const [focus, setFocus] = useState<Game | null>(null)          // clicked in the list -> map flies there
  const [selectedVenue, setSelectedVenue] = useState<string | null>(null) // clicked on the map -> list highlights
  const [tailgateFor, setTailgateFor] = useState<number | null>(null)
  const [showGameForm, setShowGameForm] = useState(false)

  const load = useCallback(() => {
    api.schedule()
      .then((s) => {
        setData(s)
        setSeason((cur) => cur ?? (s.seasons.length ? s.seasons[s.seasons.length - 1] : null))
      })
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const you: [number, number] | null = user?.lat != null && user?.lng != null ? [user.lat, user.lng] : null
  const games = useMemo(
    () => (data?.games ?? []).filter((g) => season == null || g.game_date.startsWith(String(season))),
    [data, season],
  )
  const nextGame = data?.games.find((g) => g.id === data.next_game_id) ?? null
  const postseason = games.find((g) => g.tournament)
  const mapped = games.filter((g) => g.lat != null && g.lng != null)
  const points: [number, number][] = mapped.map((g) => [g.lat!, g.lng!])
  const venues = useMemo(() => groupByVenue(games), [games])
  const [today] = useState(() => new Date().toLocaleDateString('en-CA')) // local YYYY-MM-DD
  const venueOf = (g: Game) => (g.lat != null && g.lng != null ? `${g.lat.toFixed(3)},${g.lng.toFixed(3)}` : null)

  function showInSchedule(g: Game) {
    setSelectedVenue(venueOf(g))
    document.getElementById(`game-${g.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const awayCount = games.filter((g) => g.home_away !== 'Home').length
  const closest = you && mapped.length
    ? mapped.filter((g) => g.home_away !== 'Home').reduce<{ g: Game; mi: number } | null>((best, g) => {
        const mi = milesBetween(you, [g.lat!, g.lng!])
        return !best || mi < best.mi ? { g, mi } : best
      }, null)
    : null

  async function removeTailgate(t: Tailgate) {
    if (!confirm(`Remove "${t.title}"?`)) return
    await api.deleteTailgate(t.id).catch((e: Error) => alert(e.message))
    load()
  }

  async function toggleRsvp(t: ScheduledTailgate) {
    await api.rsvp(t.id, !t.going).catch((e: Error) => alert(e.message))
    load()
  }

  async function removeGame(g: Game) {
    if (!confirm(`Delete the ${g.opponent} game and its tailgates?`)) return
    await api.deleteGame(g.id).catch((e: Error) => alert(e.message))
    load()
  }

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-text">
          <p className="eyebrow">Welcome back, {user?.first_name}</p>
          <h1>Forging Falcons, on and off the field.</h1>
          <p>
            Catch the Falcons on the road, link up with teammates at the tailgate, and keep the
            brotherhood strong long after graduation.
          </p>
          <div className="hero-actions">
            <Link to="/alumni" className="btn btn-gold">Find alumni near you</Link>
            <Link to="/mentorship" className="btn btn-outline-light">Mentor a cadet</Link>
          </div>
        </div>
        <div className="hero-card">
          {nextGame ? (
            <>
              <p className="eyebrow">Next game</p>
              <h3>{nextGame.home_away === 'Home' ? 'vs' : 'at'} {nextGame.opponent}</h3>
              <p>{fmtDate(nextGame.game_date)} · {nextGame.time_label}</p>
              <p className="muted-light">{nextGame.venue || nextGame.location}</p>
            </>
          ) : (
            <>
              <p className="eyebrow">{season ?? ''} season in review</p>
              <h3>{record(games)} overall</h3>
              {postseason && <p>Postseason: {postseason.tournament}</p>}
              <p className="muted-light">The next schedule will be posted here as soon as it's released.</p>
            </>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Schedule &amp; tailgates</h2>
            <p className="muted">
              {awayCount} road games this season. Look for a game near you and come say hello at the tailgate.
              {closest && <> Closest road game to you: <strong>{closest.g.opponent}</strong> ({Math.round(closest.mi)} mi).</>}
            </p>
          </div>
          <div className="section-tools">
            {data && data.seasons.length > 1 && (
              <select value={season ?? ''} onChange={(e) => setSeason(Number(e.target.value))} aria-label="Season">
                {data.seasons.map((s) => <option key={s} value={s}>{s} season</option>)}
              </select>
            )}
            {isAdmin && (
              <button className="btn btn-primary btn-sm" onClick={() => setShowGameForm((v) => !v)}>
                {showGameForm ? 'Close' : '+ Add game'}
              </button>
            )}
          </div>
        </div>

        {showGameForm && (
          <GameForm
            onDone={(year) => {
              setShowGameForm(false)
              setSeason(year)
              load()
            }}
          />
        )}
        {error && <div className="alert alert-error">{error}</div>}

        <div className="schedule-layout">
          <ol className="schedule-list">
            {games.map((g) => {
              const mi = you && g.lat != null ? Math.round(milesBetween(you, [g.lat, g.lng!])) : null
              return (
                <li
                  key={g.id}
                  id={`game-${g.id}`}
                  className={[
                    'game',
                    (focus?.id === g.id || (selectedVenue != null && venueOf(g) === selectedVenue)) && 'focused',
                    g.id === data?.next_game_id && 'next',
                    g.game_date < today && 'past',
                  ].filter(Boolean).join(' ')}
                >
                  <button
                    className="game-main"
                    onClick={() => {
                      setFocus(g)
                      setSelectedVenue(venueOf(g))
                    }}
                    title="Show on map"
                  >
                    <span className="game-date">
                      <strong>{fmtDate(g.game_date).split(',')[0]}</strong>
                      <span>{new Date(`${g.game_date}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                    </span>
                    <span className="game-info">
                      <span className="game-opponent">
                        <span className={`badge badge-${g.home_away.toLowerCase()}`}>{g.home_away}</span>
                        {g.home_away === 'Home' ? 'vs' : 'at'} {g.opponent}
                      </span>
                      <span className="game-meta">
                        {g.location}{g.venue && ` · ${g.venue}`}{g.tournament && ` · ${g.tournament}`}
                      </span>
                      {mi != null && g.home_away !== 'Home' && <span className="game-distance">{mi.toLocaleString()} mi from you</span>}
                    </span>
                    <span className="game-result">
                      {g.result ? (
                        <span className={isWin(g.result) ? 'win' : isLoss(g.result) ? 'loss' : ''}>{g.result}</span>
                      ) : (
                        <span>{g.time_label}</span>
                      )}
                    </span>
                  </button>

                  {g.game_date >= today && (
                    <div className="game-actions">
                      <button className="link-btn" onClick={() => addGameToCalendar(g)}>📅 Add game to calendar</button>
                    </div>
                  )}

                  {g.tailgates.length > 0 && (
                    <ul className="tailgates">
                      {g.tailgates.map((t) => {
                        const upcoming = g.game_date >= today
                        const names = t.attendees.map((a) => `${a.name} ’${String(a.grad_year).slice(2)}`)
                        return (
                          <li key={t.id} className="tailgate">
                            <span className="tailgate-icon" aria-hidden="true">⛺</span>
                            <div>
                              <strong>{t.title}</strong>
                              <span className="muted"> · {t.start_time && `${t.start_time} · `}{t.location}</span>
                              {t.details && <p>{t.details}</p>}
                              {t.host && <small className="muted">Hosted by {t.host}</small>}
                              {t.rsvp_count > 0 && (
                                <p className="rsvp-who" title={names.join(', ')}>
                                  <strong>{t.rsvp_count} {upcoming ? 'going' : 'went'}:</strong>{' '}
                                  {names.slice(0, 4).join(', ')}{names.length > 4 && ` +${names.length - 4} more`}
                                </p>
                              )}
                              {upcoming && (
                                <div className="tailgate-actions">
                                  <button
                                    className={`btn btn-sm ${t.going ? 'btn-gold' : 'btn-outline'}`}
                                    onClick={() => toggleRsvp(t)}
                                    aria-pressed={t.going}
                                  >
                                    {t.going ? "✓ I'm going" : "I'm going"}
                                  </button>
                                  <button className="link-btn" onClick={() => addTailgateToCalendar(t, g)}>📅 Add to calendar</button>
                                </div>
                              )}
                            </div>
                            {isAdmin && <button className="link-btn danger" onClick={() => removeTailgate(t)}>Remove</button>}
                          </li>
                        )
                      })}
                    </ul>
                  )}

                  {isAdmin && (
                    <div className="game-admin">
                      {tailgateFor === g.id ? (
                        <TailgateForm
                          gameId={g.id}
                          onDone={() => {
                            setTailgateFor(null)
                            load()
                          }}
                        />
                      ) : (
                        <>
                          <button className="link-btn" onClick={() => setTailgateFor(g.id)}>+ Add tailgate</button>
                          <button className="link-btn danger" onClick={() => removeGame(g)}>Delete game</button>
                        </>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
            {data && games.length === 0 && <li className="empty">No games posted for this season yet.</li>}
          </ol>

          <div className="schedule-map card">
            <MapContainer center={[39.5, -98.35]} zoom={4} scrollWheelZoom={false} className="map">
              <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} />
              <FitBounds points={you ? [...points, you] : points} />
              <FlyTo point={focus && focus.lat != null ? [focus.lat, focus.lng!] : null} />
              {venues.map((v) => {
                const first = v.games[0]
                const home = v.games.every((g) => g.home_away === 'Home')
                const past = v.games.every((g) => g.game_date < today)
                const next = v.games.some((g) => g.id === data?.next_game_id)
                const multi = v.games.length > 1
                return (
                  <Marker
                    key={v.key}
                    position={[v.lat, v.lng]}
                    icon={venueIcon({
                      label: multi ? first.location.split(',')[0] : shortDate(first.game_date),
                      sub: multi ? `${v.games.length} games` : undefined,
                      home,
                      past,
                      next,
                      active: selectedVenue === v.key,
                    })}
                    zIndexOffset={next ? 1000 : selectedVenue === v.key ? 800 : past ? 0 : 400}
                    eventHandlers={{ click: () => setSelectedVenue(v.key) }}
                  >
                    <Popup>
                      <div className="venue-popup">
                        <strong>{first.venue || first.location}</strong>
                        <small className="muted">{first.location}</small>
                        <ul>
                          {v.games.map((g) => (
                            <li key={g.id} className={g.game_date < today ? 'past' : ''}>
                              <span className="venue-popup-date">{shortDate(g.game_date)}</span>
                              <span>
                                {g.home_away === 'Home' ? 'vs' : 'at'} {g.opponent}
                                {g.result ? (
                                  <b className={isWin(g.result) ? 'win' : isLoss(g.result) ? 'loss' : ''}> {g.result}</b>
                                ) : (
                                  <small className="muted"> · {g.time_label}</small>
                                )}
                                {g.tailgates.length > 0 && <small className="venue-popup-tailgate">⛺ {g.tailgates.map((t) => t.title).join(', ')}</small>}
                              </span>
                              <button className="link-btn" onClick={() => showInSchedule(g)}>View</button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </Popup>
                  </Marker>
                )
              })}
              {you && (
                <Marker position={you} icon={youIcon} zIndexOffset={500}>
                  <Popup>You · {user?.location_label}</Popup>
                </Marker>
              )}
            </MapContainer>
            <div className="map-legend">
              <span><i className="legend-dot home" /> Home (USAFA)</span>
              <span><i className="legend-dot away" /> Away / Neutral</span>
              <span><i className="legend-dot played" /> Already played</span>
              <span><i className="legend-dot next" /> Next game</span>
              {you ? <span><i className="legend-dot you" /> You</span> : <Link to="/profile">Add your city to see distances</Link>}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

function TailgateForm({ gameId, onDone }: { gameId: number; onDone: () => void }) {
  const [t, setT] = useState({ title: '', location: '', start_time: '', details: '', host: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.addTailgate({ game_id: gameId, ...t })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <div className="form-row">
        <input required placeholder="Tailgate name" value={t.title} onChange={(e) => setT({ ...t, title: e.target.value })} />
        <input required placeholder="Where (lot, bar, park…)" value={t.location} onChange={(e) => setT({ ...t, location: e.target.value })} />
        <input placeholder="Start time" value={t.start_time} onChange={(e) => setT({ ...t, start_time: e.target.value })} />
      </div>
      <div className="form-row">
        <input placeholder="Details (food, what to bring…)" value={t.details} onChange={(e) => setT({ ...t, details: e.target.value })} />
        <input placeholder="Host (defaults to you)" value={t.host} onChange={(e) => setT({ ...t, host: e.target.value })} />
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <div className="inline-actions">
        <button className="btn btn-primary btn-sm" disabled={busy}>Save tailgate</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onDone}>Cancel</button>
      </div>
    </form>
  )
}

function GameForm({ onDone }: { onDone: (year: number) => void }) {
  const [g, setG] = useState({
    game_date: '', time_label: '', home_away: 'Away', opponent: '', location: '', venue: '', tournament: '', result: '',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await api.addGame(g as Partial<Game>)
      if (!res.mapped) alert("Game saved, but we couldn't find that city on the map. Try the format 'City, ST'.")
      onDone(Number(g.game_date.slice(0, 4)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card inline-form game-form" onSubmit={submit}>
      <h3>Add a game</h3>
      <div className="form-row">
        <label>Date<input type="date" required value={g.game_date} onChange={(e) => setG({ ...g, game_date: e.target.value })} /></label>
        <label>Time<input placeholder="12:00 PM MT" value={g.time_label} onChange={(e) => setG({ ...g, time_label: e.target.value })} /></label>
        <label>
          Site
          <select value={g.home_away} onChange={(e) => setG({ ...g, home_away: e.target.value })}>
            <option>Home</option><option>Away</option><option>Neutral</option>
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>Opponent<input required value={g.opponent} onChange={(e) => setG({ ...g, opponent: e.target.value })} /></label>
        <label>City<input required placeholder={g.home_away === 'Home' ? 'USAFA, CO' : 'City, ST'} value={g.location} onChange={(e) => setG({ ...g, location: e.target.value })} /></label>
        <label>Venue<input value={g.venue} onChange={(e) => setG({ ...g, venue: e.target.value })} /></label>
      </div>
      <div className="form-row">
        <label>Tournament (optional)<input value={g.tournament} onChange={(e) => setG({ ...g, tournament: e.target.value })} /></label>
        <label>Result (optional)<input placeholder="W 13-12" value={g.result} onChange={(e) => setG({ ...g, result: e.target.value })} /></label>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <button className="btn btn-primary btn-sm" disabled={busy}>{busy ? 'Saving…' : 'Save game'}</button>
    </form>
  )
}
