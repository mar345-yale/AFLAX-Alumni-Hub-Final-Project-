import { useEffect, useState } from 'react'

// Days from Thanksgiving (4th Thursday of November) to the campaign date.
// -2 = the Tuesday before Thanksgiving (per the project plan).
// The national #GivingTuesday is the Tuesday after Thanksgiving; use +5 for that.
const OFFSET_FROM_THANKSGIVING = -2

/** Next campaign date; rolls to next year once this year's date has passed. */
function givingTuesday(now: Date): Date {
  const forYear = (year: number) => {
    const nov1 = new Date(year, 10, 1)
    const firstThursday = 1 + ((4 - nov1.getDay() + 7) % 7)
    return new Date(year, 10, firstThursday + 21 + OFFSET_FROM_THANKSGIVING)
  }
  const thisYear = forYear(now.getFullYear())
  const endOfDay = new Date(thisYear.getTime() + 24 * 60 * 60 * 1000)
  return now < endOfDay ? thisYear : forYear(now.getFullYear() + 1)
}

function useCountdown(target: Date) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const ms = Math.max(0, target.getTime() - now.getTime())
  return {
    live: ms === 0,
    days: Math.floor(ms / 86_400_000),
    hours: Math.floor((ms / 3_600_000) % 24),
    minutes: Math.floor((ms / 60_000) % 60),
    seconds: Math.floor((ms / 1000) % 60),
  }
}

export default function Donate() {
  const [target] = useState(() => givingTuesday(new Date()))
  const t = useCountdown(target)
  const units: [string, number][] = [['Days', t.days], ['Hours', t.hours], ['Minutes', t.minutes], ['Seconds', t.seconds]]

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">Support the Team</p>
        <h1>Back the Falcons</h1>
        <p className="muted">
          Alumni gifts fund better travel, better food, and a better quality of life for the team during the season.
          Here are two ways to back the program right now.
        </p>
      </header>

      <div className="donate-grid">
        <article className="donate-card card">
          <div className="donate-icon" aria-hidden="true">🥍</div>
          <h2>Friends of Air Force Lacrosse</h2>
          <p>
            Give directly to the team through the Friends of Air Force Lacrosse. Every gift helps provide the resources
            needed to forge leaders of character and keep the Falcons competing at the highest level.
          </p>
          <a className="btn btn-primary" href="https://www.aflacrosse.org/support.html" target="_blank" rel="noreferrer">
            Give now at aflacrosse.org ↗
          </a>
        </article>

        <article className="donate-card card giving-tuesday">
          <div className="donate-icon" aria-hidden="true">💙</div>
          <h2>Giving Tuesday</h2>
          <p>
            Every year the Air Force Academy launches its Giving Tuesday campaign. Mark your calendar for{' '}
            <strong>{target.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</strong>.
          </p>
          {t.live ? (
            <p className="live-now">Giving Tuesday is today!</p>
          ) : (
            <div className="countdown" role="timer" aria-label="Countdown to Giving Tuesday">
              {units.map(([label, value]) => (
                <div key={label} className="countdown-unit">
                  <span className="countdown-value">{String(value).padStart(2, '0')}</span>
                  <span className="countdown-label">{label}</span>
                </div>
              ))}
            </div>
          )}
          <button className="btn btn-outline" disabled>Link Coming Soon</button>
        </article>
      </div>
    </div>
  )
}
