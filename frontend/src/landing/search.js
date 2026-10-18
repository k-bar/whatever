/**
 * The start page's three-part search: what (free text) · when (a day or a range) · where (district, venue,
 * event type, or an address). Every part is optional; with nothing filled in it simply opens the map.
 */
import { CATEGORIES, EVENT_TYPES, categoryLabel } from '../data/categories'
import { SEARCH_TYPES, typeLabel } from '../data/types'
import { upcoming } from '../data/api'
import { smartSearch } from '../search/engine'
import { translate } from '../i18n'

const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ł/g, 'l')

/** Typeahead for "Where": districts and neighbourhoods (areas, e.g. Saska Kępa), venues and event types. */
export function whereSuggestions(text, features, limit = 7, areas = []) {
  const needle = norm(text.trim())
  if (!needle) return []
  const out = new Map()
  const add = (kind, label, extra = {}) => { const key = `${kind}:${norm(label)}`; if (!out.has(key)) out.set(key, { kind, label, ...extra }) }
  // types first (data/types.js): "kino" -> Cinema, "muzeum" -> Museum; picking one shows only that type
  for (const id of SEARCH_TYPES) if (norm(typeLabel(id)).includes(needle)) add('type', typeLabel(id), { type: id })
  for (const [slug, et] of Object.entries(EVENT_TYPES)) if (norm(translate(et.label)).includes(needle) || norm(et.label).includes(needle)) add('type', translate(et.label), { category: et.category })
  for (const slug of Object.keys(CATEGORIES)) if (norm(categoryLabel(slug)).includes(needle)) add('type', categoryLabel(slug), { category: slug })
  for (const a of areas) if (norm(a.name).includes(needle)) add('district', a.name, a.kind === 'area' && a.district ? { sub: a.district } : {})
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
const geoCache = new Map()
export async function geocodeWarsaw(text, signal) {
  const key = text.trim().toLowerCase()
  if (geoCache.has(key)) return geoCache.get(key)
  const hits = await geocodeWarsawNow(text, signal)
  geoCache.set(key, hits)
  return hits
}
async function geocodeWarsawNow(text, signal) {
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

/** The start page's what · when · where: the same search as the map (src/search/engine.js), so areas,
 * dates and tolerances behave the same everywhere. Returns { results, exact, summary, area, understood }. */
export function landingSearch({ q = '', when, where }, features) {
  return smartSearch(q, upcoming(features), { when, where })
}
