import L from 'leaflet'

// Standard OpenStreetMap tiles: free, no API key, attribution required.
export const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
export const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

// All map markers are plain HTML/CSS (no image files), styled in App.css.
export function countIcon(count: number, selected = false): L.DivIcon {
  const size = count >= 10 ? 46 : count >= 4 ? 40 : 34
  return L.divIcon({
    className: '',
    html: `<div class="count-pin ${selected ? 'selected' : ''}" style="width:${size}px;height:${size}px"><span>${count}</span></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

interface VenuePinOptions {
  label: string        // "FEB 7" for one game, or the city for several
  sub?: string         // "6 games" when a venue hosts more than one
  home: boolean        // gold for USAFA home games, blue for road/neutral
  past: boolean        // every game here has been played -> faded
  next: boolean        // venue hosts the next upcoming game -> gold ring
  active: boolean      // selected from the list or by clicking the pin
}

/** Date-label pin for a venue. The fixed-size box keeps the anchor at the pointer tip. */
export function venueIcon(o: VenuePinOptions): L.DivIcon {
  const classes = ['venue-pin', o.home ? 'venue-home' : 'venue-away', o.past && 'past', o.next && 'next', o.active && 'active']
    .filter(Boolean)
    .join(' ')
  return L.divIcon({
    className: '',
    html: `<div class="venue-pin-wrap"><div class="${classes}">
      <span class="venue-pin-label">${escapeHtml(o.label)}</span>
      ${o.sub ? `<span class="venue-pin-sub">${escapeHtml(o.sub)}</span>` : ''}
    </div></div>`,
    iconSize: [140, 52],
    iconAnchor: [70, 52],
    popupAnchor: [0, -46],
  })
}

export const youIcon = L.divIcon({
  className: '',
  html: '<div class="you-pin"><span>You</span></div>',
  iconSize: [44, 22],
  iconAnchor: [22, 11],
})

/** Great-circle distance in statute miles. */
export function milesBetween(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const R = 3958.8
  const dLat = toRad(b[0] - a[0])
  const dLng = toRad(b[1] - a[1])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}
