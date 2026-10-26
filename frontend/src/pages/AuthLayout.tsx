import type { ReactNode } from 'react'

interface Props {
  title: string
  subtitle: string
  wide?: boolean
  children: ReactNode
}

// Split screen used by Log in and Sign up: brand panel on the left, form on the right.
export default function AuthLayout({ title, subtitle, wide, children }: Props) {
  return (
    <div className="auth-page">
      <aside className="auth-brand">
        <div className="auth-brand-inner">
          <div className="auth-logo"><img src="/afa-bird.png" alt="Air Force Falcon logo" /></div>
          <p className="eyebrow">Air Force Lacrosse · Est. 1967</p>
          <h1>Forging Falcons, on and off the field.</h1>
          <p>
            The hub for AFLAX alumni connection and cadet mentorship. Find teammates near you,
            catch the Falcons on the road, and help the next class choose their path.
          </p>
          <ul className="auth-points">
            <li>See who's where on the alumni map</li>
            <li>Tailgates for every away game</li>
            <li>AI-powered AFSC and base mentorship</li>
          </ul>
        </div>
      </aside>
      <section className="auth-panel">
        <div className={`auth-card ${wide ? 'wide' : ''}`}>
          <h2>{title}</h2>
          <p className="muted">{subtitle}</p>
          {children}
        </div>
      </section>
    </div>
  )
}
