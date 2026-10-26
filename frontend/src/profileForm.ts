import type { Status } from './api'

export interface ProfileValues {
  first_name: string
  last_name: string
  grad_year: string
  status: Status | ''
  rank: string
  afsc: string
  aircraft: string
  job: string
  base: string
  city: string
  phone: string
  willing_to_mentor: boolean
  show_phone: boolean
}

export const emptyProfile: ProfileValues = {
  first_name: '', last_name: '', grad_year: '', status: '', rank: '', afsc: '', aircraft: '',
  job: '', base: '', city: '', phone: '', willing_to_mentor: true, show_phone: true,
}

export function appendProfile(form: FormData, v: ProfileValues) {
  const fields: (keyof ProfileValues)[] = [
    'first_name', 'last_name', 'grad_year', 'status', 'rank', 'afsc', 'aircraft', 'job', 'base', 'city', 'phone',
  ]
  for (const f of fields) form.append(f, String(v[f] ?? ''))
  form.append('willing_to_mentor', String(v.status !== 'Cadet' && v.willing_to_mentor))
  form.append('show_phone', String(v.show_phone))
}
