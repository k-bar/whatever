/**
 * Thin client for the python backend (FastAPI, backend/app). Every call degrades to the
 * mock files in /public/mock when the API is unreachable, so the demo never shows an empty map.
 * API base: VITE_API_URL (default "/api", proxied by vite to http://localhost:8000).
 */
import { categoryLabel } from './categories'

const BASE = import.meta.env.VITE_API_URL || '/api'
export const WARSAW_BBOX = [20.85, 52.1, 21.27, 52.37]
export const WARSAW_CENTER = [21.012, 52.232]

export const dataStatus = { source: 'loading' } // 'api' | 'mock' | 'loading'

async function get(path, opts = {}) {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), opts.timeout ?? 2500)
  try {
    const r = await fetch(`${BASE}${path}`, { signal: ctl.signal, ...opts })
    if (!r.ok) throw new Error(r.status)
    return await r.json()
  } finally {
    clearTimeout(t)
  }
}

export async function fetchFeatures() {
  try {
    const [events, places] = await Promise.all([
      get(`/events?bbox=${WARSAW_BBOX.join(',')}&limit=2000`),
      get(`/places?bbox=${WARSAW_BBOX.join(',')}`),
    ])
    dataStatus.source = 'api'
    return { type: 'FeatureCollection', features: [...events.features, ...places.features] }
  } catch {
    dataStatus.source = 'mock'
    return (await fetch('/mock/features.geojson')).json()
  }
}

export async function fetchBusy() {
  try {
    return await get('/busy')
  } catch {
    return (await fetch('/mock/busy.geojson')).json()
  }
}

export async function fetchSources() {
  try {
    return await get('/sources')
  } catch {
    return (await fetch('/mock/sources.json')).json()
  }
}

export async function fetchMapbox(feature) {
  // backend/mapboxes will curate "the most important info" server-side; until then the
  // frontend curates locally (src/mapboxes/curate.js) and this just returns null.
  try {
    return await get(`/mapboxes/${encodeURIComponent(feature.properties.event_id)}`, { timeout: 1200 })
  } catch {
    return null
  }
}

export async function loadSettings() {
  try {
    return await get('/ui/settings', { timeout: 1200 })
  } catch {
    return null
  }
}

export async function saveSettings(values) {
  try {
    await get('/ui/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(values), timeout: 1500 })
    return true
  } catch {
    return false
  }
}

/**
 * Search. mode ∈ search | events | assistant. Tries backend/search/<mode> first, then
 * filters the already-loaded features client-side.
 */
export async function runSearch(mode, q, features, opts = {}) {
  try {
    return await get(`/search/${mode}?q=${encodeURIComponent(q)}${opts.category ? `&category=${opts.category}` : ''}`, { timeout: 1500 })
  } catch {
    return localSearch(mode, q, features, opts)
  }
}

function localSearch(mode, q, features, opts = {}) {
  if (opts.category) { // category pill: everything tagged with it, dated things first
    const list = features.filter((f) => (f.properties.categories || []).includes(opts.category))
    list.sort((a, b) => (a.properties.kind === 'event' ? 0 : 1) - (b.properties.kind === 'event' ? 0 : 1) || String(a.properties.starts_at || 'z').localeCompare(String(b.properties.starts_at || 'z')))
    return { results: list.slice(0, 80) }
  }
  const needle = q.trim().toLowerCase()
  const words = needle.split(/\s+/).filter(Boolean)
  const score = (f) => {
    const p = f.properties
    const hay = `${p.title} ${p.venue_name || ''} ${p.lead || ''} ${(p.categories || []).join(' ')} ${(p.categories || []).map(categoryLabel).join(' ')} ${p.district || ''} ${p.address || ''}`.toLowerCase()
    let s = 0
    for (const w of words) if (hay.includes(w)) s += p.title.toLowerCase().includes(w) ? 3 : 1
    return s
  }
  let pool = features
  if (mode === 'events') pool = pool.filter((f) => f.properties.kind === 'event')
  const scored = pool.map((f) => [score(f), f]).filter(([s]) => (words.length ? s > 0 : true))
  scored.sort((a, b) => b[0] - a[0] || String(a[1].properties.starts_at || 'z').localeCompare(String(b[1].properties.starts_at || 'z')))
  const results = scored.slice(0, 60).map(([, f]) => f)
  if (mode === 'assistant') {
    const n = results.length
    const cats = [...new Set(results.flatMap((f) => f.properties.categories))].slice(0, 3).join(', ')
    const top = results.slice(0, 3).map((f) => `• ${f.properties.title}${f.properties.venue_name ? ` @ ${f.properties.venue_name}` : ''}`).join('\n')
    const answer = n
      ? `I found ${n} things matching “${q}” across the city, mostly ${cats}. My top picks:\n${top}\n\nTap one to open it on the map. (Assistant is a stub: backend/search/assistant.py will plug in a real model.)`
      : `Nothing matches “${q}” yet. Try a district (Praga, Mokotów), a mood (jazz, run, picnic) or a venue.`
    return { answer, results }
  }
  return { results }
}

/* ---------- position, routing, traffic ---------- */

/** Where am I? IP geolocation (no permission prompt). Falls back to Centrum. */
export async function locateByIp() {
  try {
    const r = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(3000) })
    const j = await r.json()
    if (j.latitude && j.longitude && Math.abs(j.latitude - 52.23) < 0.6 && Math.abs(j.longitude - 21.01) < 0.8) return { lngLat: [j.longitude, j.latitude], label: j.city || 'your IP', exact: false }
    return { lngLat: WARSAW_CENTER, label: `${j.city || 'outside Warsaw'} → shown at Centrum`, exact: false }
  } catch {
    return { lngLat: WARSAW_CENTER, label: 'Centrum (IP lookup failed)', exact: false }
  }
}

const WALK_KMH = 4.8, BIKE_KMH = 15

/** Street route from → to. Public OSRM demo; walking/cycling times derived from the distance. */
export async function routeTo(from, to) {
  const url = `https://router.project-osrm.org/route/v1/foot/${from[0]},${from[1]};${to[0]},${to[1]}?overview=full&geometries=geojson`
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(6000) })
    const j = await r.json()
    const route = j.routes?.[0]
    if (!route) throw new Error('no route')
    const km = route.distance / 1000
    return { geometry: route.geometry, km, walkMin: Math.round((km / WALK_KMH) * 60), bikeMin: Math.round((km / BIKE_KMH) * 60), source: 'osrm' }
  } catch {
    const km = haversineKm(from, to) * 1.3 // street factor
    return { geometry: { type: 'LineString', coordinates: [from, to] }, km, walkMin: Math.round((km / WALK_KMH) * 60), bikeMin: Math.round((km / BIKE_KMH) * 60), source: 'estimate' }
  }
}

export function haversineKm([lng1, lat1], [lng2, lat2]) {
  const R = 6371, toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

/** High-traffic areas (Google "busy" style golden boxes). Mock until the Places API lands: GET /traffic */
export async function fetchTraffic() {
  try {
    return await get('/traffic')
  } catch {
    const boxes = [ // [lng, lat, w, h, label]
      [21.0200, 52.2310, 0.006, 0.006, 'Nowy Świat / Chmielna'], [21.0060, 52.2320, 0.006, 0.004, 'Centrum / Pałac Kultury'],
      [21.0400, 52.2410, 0.004, 0.009, 'Bulwary Wiślane'], [21.0180, 52.2240, 0.004, 0.003, 'Hala Koszyki'],
      [21.0125, 52.2200, 0.004, 0.003, 'Plac Zbawiciela'], [21.0160, 52.2495, 0.005, 0.005, 'Stare Miasto'],
      [21.0350, 52.2530, 0.005, 0.003, 'Ząbkowska'], [20.9850, 52.2320, 0.005, 0.004, 'Rondo Daszyńskiego'],
      [21.0050, 52.2290, 0.004, 0.003, 'Dworzec Centralny'], [20.9800, 52.2690, 0.004, 0.003, 'Plac Wilsona'],
    ]
    return { type: 'FeatureCollection', features: boxes.map(([x, y, w, h, label]) => ({ type: 'Feature', properties: { label, level: 'high' },
      geometry: { type: 'Polygon', coordinates: [[[x - w, y - h], [x + w, y - h], [x + w, y + h], [x - w, y + h], [x - w, y - h]]] } })) }
  }
}
