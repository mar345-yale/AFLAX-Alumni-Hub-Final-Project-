import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, session } from './api'
import type { Member } from './api'
import { AuthContext } from './useAuth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Member | null>(null)
  const [loading, setLoading] = useState(() => Boolean(session.get()))

  // Restore the session on page load.
  useEffect(() => {
    if (!session.get()) return
    api.me()
      .then(setUser)
      .catch(() => session.clear())
      .finally(() => setLoading(false))
  }, [])

  // Any 401 from the API logs the member out everywhere.
  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('aflax:logout', onLogout)
    return () => window.removeEventListener('aflax:logout', onLogout)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password)
    session.set(res.token)
    setUser(res.user)
  }, [])

  const logout = useCallback(() => {
    // Revoke the session server-side too, so a copied token stops working immediately.
    api.logout().catch(() => undefined).finally(() => {
      session.clear()
      setUser(null)
    })
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout, setUser }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
