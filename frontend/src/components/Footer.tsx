import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <img src="/afa-bird.png" alt="" />
          <div>
            <strong>Air Force Lacrosse Alumni</strong>
            <p>Forging Falcons, on and off the field.</p>
          </div>
        </div>
        <div className="footer-col">
          <h4>Portal</h4>
          <Link to="/alumni">Alumni Connection</Link>
          <Link to="/mentorship">Cadet Mentorship</Link>
          <Link to="/donate">Support the Team</Link>
        </div>
        <div className="footer-col">
          <h4>Team</h4>
          <a href="https://goairforcefalcons.com/sports/mens-lacrosse/schedule" target="_blank" rel="noreferrer">Schedule</a>
          <a href="https://goairforcefalcons.com/sports/mens-lacrosse/roster" target="_blank" rel="noreferrer">Roster</a>
          <a href="https://www.aflacrosse.org/index.html" target="_blank" rel="noreferrer">Friends of AF Lacrosse</a>
        </div>
      </div>
      <p className="footer-fine">Members-only portal. Please keep alumni and cadet contact information within the AFLAX family.</p>
    </footer>
  )
}
