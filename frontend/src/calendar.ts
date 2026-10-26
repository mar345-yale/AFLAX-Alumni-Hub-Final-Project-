// Builds .ics calendar files in the browser (no server round trip) for games and tailgates.
// Times are written as "floating" local times, i.e. shown at the clock time listed on the
// schedule. If a time can't be parsed, the event is all-day.

import type { Game, Tailgate } from './api'

function parseTime(label: string): { h: number; m: number } | null {
  const match = label.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)/i)
  if (!match) return null
  let h = Number(match[1]) % 12
  if (match[3].toLowerCase() === 'pm') h += 12
  return { h, m: Number(match[2] ?? 0) }
}

const pad = (n: number) => String(n).padStart(2, '0')
const escape = (s: string) => s.replace(/\\/g, '\\\\').replace(/([,;])/g, '\\$1').replace(/\n/g, '\\n')

function stamp(date: string, h: number, m: number): string {
  return `${date.replace(/-/g, '')}T${pad(h)}${pad(m)}00`
}

function addMinutes(date: string, h: number, m: number, minutes: number): string {
  const d = new Date(`${date}T${pad(h)}:${pad(m)}:00`)
  d.setMinutes(d.getMinutes() + minutes)
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}00`
}

function nextDay(date: string): string {
  const d = new Date(`${date}T12:00:00`)
  d.setDate(d.getDate() + 1)
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
}

function buildEvent(uid: string, title: string, date: string, timeLabel: string, minutes: number,
                    location: string, description: string): string {
  const t = parseTime(timeLabel)
  const when = t
    ? [`DTSTART:${stamp(date, t.h, t.m)}`, `DTEND:${addMinutes(date, t.h, t.m, minutes)}`]
    : [`DTSTART;VALUE=DATE:${date.replace(/-/g, '')}`, `DTEND;VALUE=DATE:${nextDay(date)}`]
  const now = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+/, '')
  return [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//AFLAX Alumni//Portal//EN', 'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT', `UID:${uid}@aflax-alumni`, `DTSTAMP:${now}`, ...when,
    `SUMMARY:${escape(title)}`, `LOCATION:${escape(location)}`, `DESCRIPTION:${escape(description)}`,
    'END:VEVENT', 'END:VCALENDAR',
  ].join('\r\n')
}

function download(filename: string, ics: string) {
  const url = URL.createObjectURL(new Blob([ics], { type: 'text/calendar;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

export function addGameToCalendar(g: Game) {
  const title = `Air Force Lacrosse ${g.home_away === 'Home' ? 'vs' : 'at'} ${g.opponent}`
  const where = [g.venue, g.location].filter(Boolean).join(', ')
  const tailgates = g.tailgates.map((t) => `Tailgate: ${t.title} (${t.start_time || 'TBA'}, ${t.location})`).join('\n')
  download(`aflax-${g.game_date}-${slug(g.opponent)}.ics`,
    buildEvent(`game-${g.id}`, title, g.game_date, g.time_label, 150, where,
      [g.tournament, tailgates, 'Go Falcons!'].filter(Boolean).join('\n')))
}

export function addTailgateToCalendar(t: Tailgate, g: Game) {
  download(`aflax-tailgate-${g.game_date}-${slug(t.title)}.ics`,
    buildEvent(`tailgate-${t.id}`, `${t.title} (AFLAX tailgate)`, g.game_date, t.start_time, 120,
      `${t.location}, ${g.location}`,
      [`Before Air Force ${g.home_away === 'Home' ? 'vs' : 'at'} ${g.opponent} (${g.time_label})`,
        t.details, t.host && `Hosted by ${t.host}`].filter(Boolean).join('\n')))
}
