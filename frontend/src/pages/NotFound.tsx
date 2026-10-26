import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="page">
      <section className="coming-soon card">
        <p className="eyebrow">404</p>
        <h1>Off target.</h1>
        <p className="muted">That page doesn't exist.</p>
        <Link to="/" className="btn btn-primary">Back to Home</Link>
      </section>
    </div>
  )
}
