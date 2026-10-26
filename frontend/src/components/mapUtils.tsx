import L from 'leaflet'
import { useEffect } from 'react'
import { useMap } from 'react-leaflet'

/** Zoom the map to fit the given points whenever they change. */
export function FitBounds({ points, maxZoom = 6 }: { points: [number, number][]; maxZoom?: number }) {
  const map = useMap()
  // Depend on a string key so a new-but-equal array doesn't re-zoom the map every render.
  const key = points.map((p) => p.join(',')).join('|')
  useEffect(() => {
    const pts = key ? key.split('|').map((s) => s.split(',').map(Number) as [number, number]) : []
    if (pts.length === 0) return
    if (pts.length === 1) {
      map.setView(pts[0], maxZoom)
      return
    }
    map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom })
  }, [key, map, maxZoom])
  return null
}

/** Fly to a point when it changes (used when a schedule row is clicked). */
export function FlyTo({ point, zoom = 7 }: { point: [number, number] | null; zoom?: number }) {
  const map = useMap()
  useEffect(() => {
    if (point) map.flyTo(point, zoom, { duration: 0.8 })
  }, [point, zoom, map])
  return null
}
