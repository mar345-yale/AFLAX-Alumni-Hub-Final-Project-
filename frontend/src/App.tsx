import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'
import Footer from './components/Footer'
import NavBar from './components/NavBar'
import Admin from './pages/Admin'
import Alumni from './pages/Alumni'
import Donate from './pages/Donate'
import Explorer from './pages/Explorer'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import Gear from './pages/Gear'
import Home from './pages/Home'
import Login from './pages/Login'
import Mentorship from './pages/Mentorship'
import NotFound from './pages/NotFound'
import Profile from './pages/Profile'
import Signup from './pages/Signup'

// Members-only shell: anyone not logged in is sent to the login page.
function Protected() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return (
    <div className="app-shell">
      <NavBar />
      <main className="app-main">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

function AdminOnly() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <Outlet /> : <Navigate to="/" replace />
}

function PublicOnly() {
  const { user, loading } = useAuth()
  if (loading) return <div className="page-loading">Loading…</div>
  return user ? <Navigate to="/" replace /> : <Outlet />
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
      </Route>
      {/* Reachable even while logged in (the link arrives by email). */}
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<Protected />}>
        <Route path="/" element={<Home />} />
        <Route path="/alumni" element={<Alumni />} />
        <Route path="/mentorship" element={<Mentorship />} />
        <Route path="/explorer" element={<Explorer />} />
        <Route path="/gear" element={<Gear />} />
        <Route path="/donate" element={<Donate />} />
        <Route path="/profile" element={<Profile />} />
        <Route element={<AdminOnly />}>
          <Route path="/admin" element={<Admin />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
