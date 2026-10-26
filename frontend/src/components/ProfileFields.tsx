import type { Options, Status } from '../api'
import type { ProfileValues } from '../profileForm'

interface Props {
  values: ProfileValues
  options: Options
  onChange: (patch: Partial<ProfileValues>) => void
}

// Formats digits as (719) 555-0100 while typing.
function formatPhone(raw: string): string {
  const d = raw.replace(/\D/g, '').slice(0, 10)
  if (d.length < 4) return d
  if (d.length < 7) return `(${d.slice(0, 3)}) ${d.slice(3)}`
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
}

/** Name, class, military status, and the fields that appear for each status:
 *  Active Duty / Guard-Reserve -> rank, AFSC, (aircraft if rated), job, base
 *  Civilian -> job, city or ZIP. Shared by sign-up and Edit Profile. */
export default function ProfileFields({ values, options, onChange }: Props) {
  const military = values.status === 'Active Duty' || values.status === 'Guard/Reserve'
  const civilian = values.status === 'Civilian'
  const aircrew = options.aircrew_afscs.includes(values.afsc)
  const rated = options.afscs.filter((a) => a.category === 'Rated')
  const nonrated = options.afscs.filter((a) => a.category !== 'Rated')

  return (
    <>
      <div className="form-row">
        <label>
          First name
          <input required value={values.first_name} onChange={(e) => onChange({ first_name: e.target.value })} autoComplete="given-name" />
        </label>
        <label>
          Last name
          <input required value={values.last_name} onChange={(e) => onChange({ last_name: e.target.value })} autoComplete="family-name" />
        </label>
      </div>

      <div className="form-row">
        <label>
          Graduation year
          <select required value={values.grad_year} onChange={(e) => onChange({ grad_year: e.target.value })}>
            <option value="">Select class year</option>
            {options.grad_years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label>
          Military status
          <select
            required
            value={values.status}
            onChange={(e) => onChange({ status: e.target.value as Status })}
          >
            <option value="">Select status</option>
            {options.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>

      {military && (
        <fieldset className="conditional">
          <legend>{values.status} details</legend>
          <div className="form-row">
            <label>
              Current rank
              <select required value={values.rank} onChange={(e) => onChange({ rank: e.target.value })}>
                <option value="">Select rank</option>
                {options.ranks.map((r) => <option key={r.code} value={r.code}>{r.code} · {r.title}</option>)}
              </select>
            </label>
            <label>
              Current AFSC
              <select
                required
                value={values.afsc}
                onChange={(e) => onChange({ afsc: e.target.value, aircraft: options.aircrew_afscs.includes(e.target.value) ? values.aircraft : '' })}
              >
                <option value="">Select AFSC</option>
                <optgroup label="Rated">
                  {rated.map((a) => <option key={a.code} value={a.code}>{a.code} · {a.title}</option>)}
                </optgroup>
                <optgroup label="Nonrated">
                  {nonrated.map((a) => <option key={a.code} value={a.code}>{a.code} · {a.title}</option>)}
                </optgroup>
              </select>
            </label>
          </div>
          {aircrew && (
            <label>
              Aircraft
              <select value={values.aircraft} onChange={(e) => onChange({ aircraft: e.target.value })}>
                <option value="">Select aircraft</option>
                {options.aircraft.map((a) => (
                  <option key={a.designation} value={a.designation}>{a.designation} {a.name} ({a.role})</option>
                ))}
              </select>
            </label>
          )}
          <div className="form-row">
            <label>
              Current job
              <input value={values.job} onChange={(e) => onChange({ job: e.target.value })} placeholder="e.g. Flight Commander" />
            </label>
            <label>
              Current base
              <select required value={values.base} onChange={(e) => onChange({ base: e.target.value })}>
                <option value="">Select base</option>
                {options.bases.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
          </div>
        </fieldset>
      )}

      {civilian && (
        <fieldset className="conditional">
          <legend>Civilian details</legend>
          <div className="form-row">
            <label>
              Current job
              <input value={values.job} onChange={(e) => onChange({ job: e.target.value })} placeholder="e.g. Airline Captain" />
            </label>
            <label>
              Current city
              <input required value={values.city} onChange={(e) => onChange({ city: e.target.value })} placeholder="City, ST or ZIP" />
            </label>
          </div>
        </fieldset>
      )}

      <label>
        Phone number
        <input
          type="tel"
          value={values.phone}
          onChange={(e) => onChange({ phone: formatPhone(e.target.value) })}
          placeholder="(719) 555-0100"
          autoComplete="tel"
        />
      </label>

      {values.phone && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={!values.show_phone}
            onChange={(e) => onChange({ show_phone: !e.target.checked })}
          />
          <span>Hide my phone number from the member roster and mentor cards (the alumni board can still see it).</span>
        </label>
      )}

      {values.status && values.status !== 'Cadet' && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={values.willing_to_mentor}
            onChange={(e) => onChange({ willing_to_mentor: e.target.checked })}
          />
          <span>I'm willing to mentor cadets. Falcon Mentor may suggest me as a contact.</span>
        </label>
      )}
    </>
  )
}
