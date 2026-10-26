import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../useAuth'
import Avatar from './Avatar'

const LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/alumni', label: 'Alumni Connection' },
  { to: '/mentorship', label: 'Cadet Mentorship' },
  { to: '/explorer', label: 'Explorer' },
  { to: '/gear', label: 'AFLAX Gear' },
  { to: '/donate', label: 'Donate' },
]

export default function NavBar() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand" aria-label="AFLAX Alumni Connections home">
          <span className="brand-logo"><img src="/afa-bird.png" alt="" /></span>
          <span className="brand-text">
            <strong>AFLAX</strong>
            <small>Alumni Connections</small>
          </span>
        </Link>
        <button className="nav-toggle" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span /><span /><span />
        </button>
        {/* Clicking any link inside closes the mobile menu. */}
        <nav className={`nav-links ${open ? 'open' : ''}`} onClick={(e) => (e.target as HTMLElement).closest('a') && setOpen(false)}>
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {l.label}
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink to="/admin" className={({ isActive }) => `board-link ${isActive ? 'active' : ''}`}>
              Board
            </NavLink>
          )}
          <div className="nav-user">
            <NavLink to="/profile" className="nav-profile" title="My profile">
              {user && <Avatar first={user.first_name} last={user.last_name} photo={user.photo_url} size={32} />}
              <span>{user?.first_name}</span>
            </NavLink>
            <button className="btn btn-ghost btn-sm" onClick={logout}>Log out</button>
          </div>
        </nav>
      </div>
    </header>
  )
}
