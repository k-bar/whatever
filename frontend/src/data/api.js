/**
 * Thin client for the python backend (FastAPI, backend/app). Every call degrades to the
 * mock files in /public/mock when the API is unreachable, so the demo never shows an empty map.
 * API base: VITE_API_URL (default "/api", proxied by vite to http://localhost:8000).
 */
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
export async function runSearch(mode, q, features) {
  try {
    return await get(`/search/${mode}?q=${encodeURIComponent(q)}`, { timeout: 1500 })
  } catch {
    return localSearch(mode, q, features)
  }
}

function localSearch(mode, q, features) {
  const needle = q.trim().toLowerCase()
  const words = needle.split(/\s+/).filter(Boolean)
  const score = (f) => {
    const p = f.properties
    const hay = `${p.title} ${p.venue_name || ''} ${p.lead || ''} ${(p.categories || []).join(' ')} ${p.district || ''} ${p.address || ''}`.toLowerCase()
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
