/**
 * Warsaw's districts and neighbourhoods (public/warsaw_areas.geojson, built by scripts/build_areas.py from
 * OpenStreetMap). Search uses them to find what is *in* an area by location: many venues have no district
 * field, so "nightlife in Śródmieście" must not depend on it. The map draws the searched area dashed.
 */
export const fold = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ł/g, 'l')
  .replace(/[-–—/.,;:!?()"„”'’]/g, ' ').replace(/\s+/g, ' ').trim()

let cache = null

/** All areas, loaded once: { name, kind: 'district' | 'area', district, tokens, bbox, feature }. */
export function loadAreas() {
  if (!cache) {
    cache = fetch(`${import.meta.env.BASE_URL || '/'}warsaw_areas.geojson`)
      .then((r) => r.json())
      .then((fc) => fc.features.map((feature) => {
        const { name, kind, district } = feature.properties
        return { name, kind, district, tokens: fold(name).split(' '), bbox: bboxOf(feature.geometry), feature }
      }))
      .catch(() => { cache = null; return [] })
  }
  return cache
}

function polygons(geometry) {
  return geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : []
}

function bboxOf(geometry) {
  let w = 180, s = 90, e = -180, n = -90
  for (const poly of polygons(geometry)) for (const [x, y] of poly[0]) { w = Math.min(w, x); s = Math.min(s, y); e = Math.max(e, x); n = Math.max(n, y) }
  return [w, s, e, n]
}

function inRing([x, y], ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

/** Is [lng, lat] inside the area (outer ring, minus holes)? */
export function contains(area, pt) {
  const [w, s, e, n] = area.bbox
  if (!pt || pt[0] < w || pt[0] > e || pt[1] < s || pt[1] > n) return false
  return polygons(area.feature.geometry).some(([outer, ...holes]) => inRing(pt, outer) && !holes.some((h) => inRing(pt, h)))
}

const KM_LAT = 111.32
/** Distance in km from a point outside the area to its edge (0 inside). Cheap: local flat projection. */
export function kmOutside(area, pt) {
  if (!pt) return Infinity
  if (contains(area, pt)) return 0
  const kx = KM_LAT * Math.cos((pt[1] * Math.PI) / 180)
  const [w, s, e, n] = area.bbox
  const dx = Math.max(w - pt[0], 0, pt[0] - e) * kx, dy = Math.max(s - pt[1], 0, pt[1] - n) * KM_LAT
  if (Math.hypot(dx, dy) > 2) return Math.hypot(dx, dy) // far: the bbox distance is enough
  let best = Infinity
  for (const poly of polygons(area.feature.geometry)) {
    const ring = poly[0]
    for (let i = 1; i < ring.length; i++) {
      const ax = (ring[i - 1][0] - pt[0]) * kx, ay = (ring[i - 1][1] - pt[1]) * KM_LAT
      const bx = (ring[i][0] - pt[0]) * kx, by = (ring[i][1] - pt[1]) * KM_LAT
      const vx = bx - ax, vy = by - ay
      const t = Math.max(0, Math.min(1, -(ax * vx + ay * vy) / (vx * vx + vy * vy || 1)))
      best = Math.min(best, Math.hypot(ax + t * vx, ay + t * vy))
    }
  }
  return best
}
