/**
 * The start page's three-part search: what (free text) · when (a day or a range) · where (district, venue,
 * event type, or an address). Every part is optional; with nothing filled in it simply opens the map.
 */
import { CATEGORIES, EVENT_TYPES, categoryLabel } from '../data/categories'
import { haversineKm } from '../data/api'
import { translate } from '../i18n'

const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ł/g, 'l')
const PLACE_RADIUS_KM = 1.5

/** Typeahead for "Where": districts, venues and event types from the loaded pins. */
export function whereSuggestions(text, features, limit = 7) {
  const needle = norm(text.trim())
  if (!needle) return []
  const out = new Map()
  const add = (kind, label, extra = {}) => { const key = `${kind}:${norm(label)}`; if (!out.has(key)) out.set(key, { kind, label, ...extra }) }
  for (const [slug, et] of Object.entries(EVENT_TYPES)) if (norm(translate(et.label)).includes(needle) || norm(et.label).includes(needle)) add('type', translate(et.label), { category: et.category })
  for (const slug of Object.keys(CATEGORIES)) if (norm(categoryLabel(slug)).includes(needle)) add('type', categoryLabel(slug), { category: slug })
  for (const f of features || []) {
    const p = f.properties
    if (p.district && norm(p.district).includes(needle)) add('district', p.district)
  }
  for (const f of features || []) {
    const p = f.properties
    if (out.size >= limit * 3) break
    if (p.venue_name && norm(p.venue_name).includes(needle)) add('venue', p.venue_name, { lngLat: f.geometry?.coordinates })
  }
  const rank = { type: 0, district: 1, venue: 2 }
  return [...out.values()]
    .sort((a, b) => Number(!norm(a.label).startsWith(needle)) - Number(!norm(b.label).startsWith(needle)) || rank[a.kind] - rank[b.kind])
    .slice(0, limit)
}

/** Addresses and landmarks in Warsaw (OpenStreetMap Nominatim) for "Where". */
export async function geocodeWarsaw(text, signal) {
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=4&countrycodes=pl&bounded=1&viewbox=20.85,52.37,21.27,52.10&q=${encodeURIComponent(text)}`
  const j = await (await fetch(url, { signal })).json()
  return j.map((r) => ({ kind: 'place', label: r.display_name.split(',').slice(0, 2).join(','), lngLat: [+r.lon, +r.lat] }))
}

/** Quick picks for "When". Each returns { label, from, to, window } (dates are local days). */
export function whenPresets() {
  const day = (offset) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + offset); return d }
  const dow = new Date().getDay() // 0 Sun .. 6 Sat
  const toSat = dow === 0 ? -1 : 6 - dow
  return [
    { label: translate('Today'), from: day(0), to: day(0), window: 'today' },
    { label: translate('Tomorrow'), from: day(1), to: day(1) },
    { label: translate('This weekend'), from: day(Math.max(0, toSat)), to: day(dow === 0 ? 0 : toSat + 1), window: 'weekend' },
    { label: translate('Next 7 days'), from: day(0), to: day(6), window: 'week' },
  ]
}

/** The map's time toggle that best covers a chosen range (the results list is exact). */
export function windowFor(when) {
  if (!when) return null
  if (when.window) return when.window
  const days = (when.to - startOfDay(new Date())) / 864e5
  return days < 1 ? 'today' : days < 7 ? 'week' : 'month'
}
const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }

/** Run the three-part search over the loaded pins. Returns the matches, best first. */
export function landingSearch({ q = '', when, where }, features) {
  let pool = features || []
  if (when) {
    const from = startOfDay(when.from), to = startOfDay(when.to); to.setDate(to.getDate() + 1)
    pool = pool.filter(({ properties: p }) => {
      if (!p.starts_at) return false
      const s = new Date(p.starts_at), e = p.ends_at ? new Date(p.ends_at) : s
      return s < to && e >= from
    })
  }
  let near = null
  if (where) {
    const w = norm(where.label)
    if (where.kind === 'type') pool = pool.filter(({ properties: p }) => (p.categories || []).includes(where.category))
    else if (where.kind === 'district') pool = pool.filter(({ properties: p }) => norm(p.district) === w)
    else if (where.kind === 'venue') pool = pool.filter(({ properties: p }) => norm(p.venue_name) === w)
    else if (where.kind === 'place' && where.lngLat) {
      near = (f) => haversineKm(where.lngLat, f.geometry.coordinates)
      pool = pool.filter((f) => f.geometry && near(f) <= PLACE_RADIUS_KM)
    } else pool = pool.filter(({ properties: p }) => norm(`${p.district} ${p.venue_name} ${p.address} ${(p.categories || []).map(categoryLabel).join(' ')}`).includes(w))
  }
  const words = norm(q).split(/\s+/).filter(Boolean)
  const score = ({ properties: p }) => {
    const title = norm(p.title)
    const hay = `${title} ${norm(p.venue_name)} ${norm(p.lead)} ${norm(p.district)} ${(p.categories || []).map((c) => norm(categoryLabel(c))).join(' ')}`
    return words.reduce((s, w) => s + (title.includes(w) ? 3 : hay.includes(w) ? 1 : 0), 0)
  }
  let scored = pool.map((f) => [words.length ? score(f) : 1, f]).filter(([s]) => s > 0)
  scored.sort((a, b) => b[0] - a[0] || (near ? near(a[1]) - near(b[1]) : 0) || String(a[1].properties.starts_at || 'z').localeCompare(String(b[1].properties.starts_at || 'z')))
  return scored.slice(0, 80).map(([, f]) => f)
}
