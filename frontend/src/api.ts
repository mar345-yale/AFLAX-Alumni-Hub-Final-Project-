// Typed client for the FastAPI backend. Every request carries the session token when
// there is one; a 401 clears the session so the app falls back to the login page.

export type Status = 'Cadet' | 'Active Duty' | 'Guard/Reserve' | 'Civilian'

export interface Member {
  id: number
  email: string
  first_name: string
  last_name: string
  grad_year: number
  status: Status
  rank: string | null
  afsc: string | null
  aircraft: string | null
  job: string | null
  base: string | null
  city: string | null
  phone: string | null
  photo_url: string | null
  willing_to_mentor: boolean
  show_phone: boolean
  role: 'member' | 'admin'
  location_label: string | null
  lat: number | null
  lng: number | null
}

export interface Rank { code: string; title: string; abbr: string }
export interface Afsc { code: string; title: string; category: string }
export interface Aircraft { designation: string; name: string; role: string }

export interface Options {
  statuses: Status[]
  ranks: Rank[]
  afscs: Afsc[]
  aircrew_afscs: string[]
  aircraft: Aircraft[]
  bases: string[]
  grad_years: number[]
}

export interface Tailgate {
  id: number
  game_id: number
  title: string
  location: string
  start_time: string
  details: string
  host: string
}

export interface Attendee { id: number; name: string; grad_year: number }

export interface ScheduledTailgate extends Tailgate {
  rsvp_count: number
  going: boolean
  attendees: Attendee[]
}

export interface Game {
  id: number
  game_date: string
  time_label: string
  home_away: 'Home' | 'Away' | 'Neutral'
  opponent: string
  location: string
  venue: string
  tournament: string
  result: string
  lat: number | null
  lng: number | null
  tailgates: ScheduledTailgate[]
}

export interface Schedule { games: Game[]; next_game_id: number | null; seasons: number[] }

export interface Pin { label: string; lat: number; lng: number; count: number }

export interface RosterEntry {
  id: number
  last_name: string
  first_name: string
  grad_year: number
  status: Status
  rank: string | null
  afsc: string | null
  afsc_title: string | null
  aircraft: string | null
  job: string | null
  location: string | null
  phone: string | null
  phone_hidden: boolean
  email: string
  photo_url: string | null
  willing_to_mentor: boolean
}

export interface AlumniResult {
  pins: Pin[]
  roster: RosterEntry[]
  total: number
  unmapped: number
  facets: { statuses: Status[]; bases: string[]; afscs: [string, string | null][] }
}

export interface MentorCard {
  id: number
  first_name: string
  last_name: string
  grad_year: number
  status: Status
  rank: string | null
  afsc: string | null
  afsc_title: string | null
  aircraft: string | null
  job: string | null
  location: string | null
  email: string
  phone: string | null
  photo_url: string | null
}

export interface IntroEmail { mentor_id: number; to: string; subject: string; body: string }

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  mentors: MentorCard[]
  intro_email: IntroEmail | null
}

export interface UsageTotals {
  messages: number
  requests: number
  tool_calls: number
  input_tokens: number
  cache_read_tokens: number
  output_tokens: number
  reasoning_tokens: number
  avg_ms: number
  errors: number
  est_cost_usd: number | null
}

export interface Usage {
  totals: { today: UsageTotals; '7d': UsageTotals; '30d': UsageTotals }
  top_users: { name: string; messages: number; tokens: number }[]
  recent: {
    created_at: string; name: string; requests: number; tool_calls: number; input_tokens: number
    cache_read_tokens: number; output_tokens: number; duration_ms: number; status: string
  }[]
  daily_limit: number
}

export interface ExploreAfsc {
  code: string
  title: string
  category: string
  overview: string
  keywords: string[]
  alumni_count: number
}

export interface ExploreAlumnus {
  id: number
  first_name: string
  last_name: string
  grad_year: number
  status: Status
  rank: string | null
  afsc: string | null
  afsc_title: string | null
  job: string | null
  location: string | null
  email: string
  phone: string | null
  photo_url: string | null
  willing_to_mentor: boolean
}

export interface AfscDetail extends Omit<ExploreAfsc, 'keywords' | 'alumni_count'> {
  training: string
  lifestyle: string
  good_fit: string
  typical_bases: string[]
  official_description: string
  alumni: ExploreAlumnus[]
}

export interface ExploreBase {
  name: string
  region: string
  type: string
  nearby_city: string
  missions: string[]
  aircraft: string[]
  cost_of_living: string
  alumni_count: number
}

export interface BaseDetail extends Omit<ExploreBase, 'alumni_count'> {
  lat: number
  lng: number
  pros: string[]
  cons: string[]
  alumni: ExploreAlumnus[]
}

export interface AdminAccount extends Member {
  approval: 'pending' | 'approved' | 'rejected'
  created_at: string
  source: string
}

const TOKEN_KEY = 'aflax_token'

export const session = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// FastAPI returns {detail: string} for our errors and {detail: [{msg}]} for validation.
function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg).replace(/^Value error, /, '') : ''))
        .filter(Boolean)
        .join(' ')
    }
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = session.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError(0, "Can't reach the server. Make sure the backend is running.")
  }
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && token) {
      session.clear()
      window.dispatchEvent(new Event('aflax:logout'))
    }
    throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`))
  }
  return body as T
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
})

export const api = {
  options: () => request<Options>('/api/options'),
  login: (email: string, password: string) =>
    request<{ token: string; user: Member }>('/api/auth/login', json('POST', { email, password })),
  signup: (form: FormData) => request<{ message: string }>('/api/auth/signup', { method: 'POST', body: form }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  forgotPassword: (email: string) => request<{ message: string }>('/api/auth/forgot', json('POST', { email })),
  resetPassword: (token: string, new_password: string) =>
    request<{ message: string }>('/api/auth/reset', json('POST', { token, new_password })),
  me: () => request<Member>('/api/me'),
  updateMe: (form: FormData) => request<Member>('/api/me', { method: 'PUT', body: form }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>('/api/me/password', json('POST', { current_password, new_password })),

  schedule: () => request<Schedule>('/api/schedule'),
  addGame: (g: Partial<Game>) => request<{ id: number; mapped: boolean }>('/api/games', json('POST', g)),
  deleteGame: (id: number) => request<void>(`/api/games/${id}`, { method: 'DELETE' }),
  addTailgate: (t: Omit<Tailgate, 'id'>) => request<{ id: number }>('/api/tailgates', json('POST', t)),
  updateTailgate: (t: Tailgate) => request<{ id: number }>(`/api/tailgates/${t.id}`, json('PUT', t)),
  deleteTailgate: (id: number) => request<void>(`/api/tailgates/${id}`, { method: 'DELETE' }),
  rsvp: (id: number, going: boolean) =>
    request<void>(`/api/tailgates/${id}/rsvp`, { method: going ? 'POST' : 'DELETE' }),

  exploreAfscs: () => request<ExploreAfsc[]>('/api/explore/afscs'),
  exploreAfsc: (code: string) => request<AfscDetail>(`/api/explore/afscs/${encodeURIComponent(code)}`),
  exploreBases: () => request<ExploreBase[]>('/api/explore/bases'),
  exploreBase: (name: string) => request<BaseDetail>(`/api/explore/bases/${encodeURIComponent(name)}`),

  alumni: (filters: Record<string, string>) => {
    const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString()
    return request<AlumniResult>(`/api/alumni${qs ? `?${qs}` : ''}`)
  },

  chat: (message: string) =>
    request<{ reply: string; mentors: MentorCard[]; intro_email: IntroEmail | null }>(
      '/api/chat', json('POST', { message })),
  chatHistory: () => request<ChatMessage[]>('/api/chat/history'),
  resetChat: () => request<void>('/api/chat/history', { method: 'DELETE' }),

  accounts: () => request<{ accounts: AdminAccount[] }>('/api/admin/accounts'),
  usage: () => request<Usage>('/api/admin/usage'),
  approve: (id: number) => request<unknown>(`/api/admin/accounts/${id}/approve`, { method: 'POST' }),
  reject: (id: number) => request<unknown>(`/api/admin/accounts/${id}/reject`, { method: 'POST' }),
  setRole: (id: number, role: 'member' | 'admin') =>
    request<unknown>(`/api/admin/accounts/${id}/role`, json('POST', { role })),
}

export const rankAbbr: Record<string, string> = {
  'O-1': '2d Lt', 'O-2': '1st Lt', 'O-3': 'Capt', 'O-4': 'Maj', 'O-5': 'Lt Col',
  'O-6': 'Col', 'O-7': 'Brig Gen', 'O-8': 'Maj Gen', 'O-9': 'Lt Gen',
}
