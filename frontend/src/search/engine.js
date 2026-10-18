/**
 * Search with tolerances. Every pin gets three scores (2 = clearly yes, 1 = close, 0 = no) for each part
 * the person asked about:
 *
 *   what  — its category, or a related one / the word in its title (a "Koncert" filed under culture)
 *   when  — dated things overlapping the day(s); venues have no date: "open places", certain for nightlife
 *   where — inside the area's outline (by location, not the district field), or within 400 m of it
 *
 * Exact matches (all 2s) come first, then close matches (any 1s). Nothing scoring 0 on a part that was
 * asked about is shown. Past events are never searched (they stay stored).
 */
import { categoryLabel } from '../data/categories'
import { typeLabel, typeOf } from '../data/types'
import { locale, translate } from '../i18n'
import { contains, fold, kmOutside, loadAreas } from './areas'
import { understand } from './understand'

const NEAR_KM = 0.4
const PLACE_RADIUS_KM = 1.5
const EVENING_HOUR = 17
const MAX_RESULTS = 120
// asked for X: these categories are close matches
const RELATED = {
  nightlife: ['music', 'festivals'], music: ['festivals', 'nightlife', 'culture'], theatre: ['culture', 'film'],
  film: ['culture', 'festivals'], exhibitions: ['culture'], culture: ['exhibitions', 'theatre', 'music', 'film'],
  festivals: ['music', 'culture'], family: ['education'], running: ['sports'], sports: ['running', 'yoga'],
  yoga: ['sports', 'health'], meetups: ['education', 'business'], education: ['meetups'],
}
// words in a title that mean the category even when the source filed it elsewhere (whole words, on the
// folded title: "party" must not match "Partyzantów", "seans" must not match "Seanse saunowe")
const TITLE_WORDS = {
  nightlife: /\b(party|parties|impreza|imprezy|dj|clubbing|techno|potancowka|dancing|disco)\b/,
  music: /\b(koncert\w*|concert\w*|jazz\w*|recital\w*|filharmon\w*|opera)\b/,
  theatre: /\b(spektakl\w*|teatr\w*|stand up|kabaret\w*)\b/,
  film: /\b(kino|kina|film|filmu|filmy|filmowy|filmowe|premiera filmu)\b/,
  exhibitions: /\b(wystaw\w*|exhibition\w*|wernisaz\w*|galeri\w*|muzeum)\b/,
}
// venues with no date are a full answer for these (a bar is open on Saturday night)
const VENUE_INTENTS = new Set(['nightlife'])

const parse = (iso) => new Date(String(iso).replace(/([+-]\d{2})$/, '$1:00'))
const dayEnd = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() + 1); return x }

function whatScore(p, cats, title) {
  if (!cats.length) return 2
  const mine = p.categories || []
  if (cats.some((c) => mine.includes(c))) return 2
  if (cats.some((c) => TITLE_WORDS[c]?.test(title))) return 2 // the title, not the description
  if (cats.some((c) => (RELATED[c] || []).some((r) => mine.includes(r)))) {
    // a concert counts as nightlife only when it's at night
    if (cats.includes('nightlife') && p.starts_at && parse(p.starts_at).getHours() < 19) return 0
    return 1
  }
  return 0
}

const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
// "17:00-02:00" / "10:00-14:00,16:00-23:00": open into the evening?
const lateSpan = (span) => String(span).split(',').some((part) => {
  const [o, c] = part.trim().split('-').map((t) => parseInt(t, 10))
  return c >= 19 || c < o
})

/** Venue opening hours ({ monday: "17:00-02:00", ... }) on the asked day(s): 2 open (late enough), 1 open earlier, 0 closed. */
function hoursScore(hours, when, evening, now) {
  const from = new Date(when ? when.from : now); from.setHours(0, 0, 0, 0)
  const days = []
  for (let d = new Date(from); days.length < 7 && d < dayEnd(when ? when.to : now); d.setDate(d.getDate() + 1)) days.push(WEEKDAYS[d.getDay()])
  const spans = days.map((d) => hours[d]).filter(Boolean)
  if (!spans.length) return 0
  return !evening || spans.some(lateSpan) ? 2 : 1
}

function whenScore(p, when, evening, cats, now) {
  if (!p.starts_at) {
    if (p.kind !== 'place') return when || evening ? 0 : 2
    if (p.opening_hours && typeof p.opening_hours === 'object' && (when || evening)) return hoursScore(p.opening_hours, when, evening, now)
    return cats.some((c) => VENUE_INTENTS.has(c)) || (!when && !evening) ? 2 : 1
  }
  const s = parse(p.starts_at), e = p.ends_at ? parse(p.ends_at) : s
  if (e < now) return 0
  if (when) {
    const from = new Date(when.from); from.setHours(0, 0, 0, 0)
    if (!(s < dayEnd(when.to) && e >= from)) return 0
  }
  if (!evening) return 2
  const startsLate = s.getHours() >= EVENING_HOUR || s.getHours() < 5
  const multiDay = e - s > 20 * 3600e3
  return startsLate ? 2 : multiDay || e.getHours() >= 20 ? 1 : 0
}

function whereScore(f, where) {
  if (!where) return 2
  const p = f.properties, pt = f.geometry?.coordinates
  if (where.area) {
    if (pt) {
      if (contains(where.area, pt)) return 2
      return kmOutside(where.area, pt) <= NEAR_KM ? 1 : 0
    }
    if (p.district && fold(p.district) === fold(where.area.name)) return 2
    return where.area.district && p.district === where.area.district ? 1 : 0
  }
  if (where.venue) return fold(p.venue_name) === fold(where.venue) ? 2 : 0
  if (where.lngLat && pt) {
    const km = Math.hypot((pt[0] - where.lngLat[0]) * 68, (pt[1] - where.lngLat[1]) * 111.3)
    return km <= PLACE_RADIUS_KM ? 2 : km <= PLACE_RADIUS_KM * 2 ? 1 : 0
  }
  if (where.text) return fold(`${p.district} ${p.venue_name} ${p.address}`).includes(fold(where.text)) ? 2 : 0
  return 2
}

function termScore(terms, title, rest) {
  let s = 0
  for (const t of terms) {
    const stem = t.length > 5 ? t.slice(0, -2) : t // koncertu -> koncer, mokotowie -> mokotow
    if (title.includes(t) || title.includes(stem)) s += 3
    else if (rest.includes(t) || rest.includes(stem)) s += 1
  }
  return s
}

/** A "Where" choice -> the engine's where ({ area } | { venue } | { lngLat } | { text }) and the outline to draw. */
export function resolveWhere(w, areas, now = new Date()) {
  if (!w) return { where: null, area: null }
  const asArea = (a) => ({ name: a.name, kind: a.kind, district: a.district, bbox: a.bbox, feature: a.feature, ref: a })
  if (w.kind === 'district' || w.kind === 'area') {
    const a = areas.find((x) => fold(x.name) === fold(w.label))
    return a ? { where: { area: a }, area: asArea(a) } : { where: { text: w.label }, area: null }
  }
  if (w.kind === 'venue') return { where: { venue: w.label }, area: null }
  if (w.kind === 'place' && w.lngLat) return { where: { lngLat: w.lngLat }, area: null }
  if (w.label) { // typed text: an area name if it is one ("Saska Kępa"), else a place-ish text match
    const parsed = understand(w.label, areas, now)
    return parsed.area ? { where: { area: parsed.area.ref }, area: parsed.area } : { where: { text: w.label }, area: null }
  }
  return { where: null, area: null }
}

/** For the map's live filter: does a pin pass When and Where (close matches included, like the results)? */
export function passesWhenWhere(f, when, where, now = new Date()) {
  return whenScore(f.properties, when, false, [], now) > 0 && whereScore(f, where) > 0
}

export function whenLabel(when) {
  if (!when) return null
  if (when.label) return when.label
  if (when.key === 'today') return translate('Today')
  if (when.key === 'tomorrow') return translate('Tomorrow')
  if (when.key === 'weekend') return translate('This weekend')
  if (when.key === 'week') return translate('Next 7 days')
  const f = (d) => new Date(d).toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
  return new Date(when.from).toDateString() === new Date(when.to).toDateString() ? f(when.from) : `${f(when.from)} – ${f(when.to)}`
}

/**
 * query: typed text. opts: { mode: 'search' | 'events' | 'assistant', category, type (data/types.js: only pins
 * of that type), when, where (start page: { kind: 'district' | 'type' | 'venue' | 'place' | 'text', label,
 * category?, type?, lngLat? }), now }.
 * Returns { results, exact, understood, summary, area } — area is the outline feature to draw, if any.
 */
export async function smartSearch(query, features, opts = {}) {
  const now = opts.now || new Date()
  const areas = await loadAreas()
  const u = understand(query || '', areas, now)
  if (opts.category && !u.categories.includes(opts.category)) u.categories.push(opts.category)
  if (opts.when) u.when = opts.when
  let where = u.area ? { area: u.area.ref } : null
  const w = opts.where
  const type = opts.type || (w?.kind === 'type' && w.type) || null
  if (w?.kind === 'type') { if (w.category && !u.categories.includes(w.category)) u.categories.push(w.category) }
  else if (w) {
    const r = resolveWhere(w, areas, now)
    if (r.where) where = r.where
    if (r.area) u.area = r.area
  }
  const structured = u.categories.length || u.when || u.evening || where || type
  const scored = []
  for (const f of features || []) {
    const p = f.properties
    if (opts.allowed) { if (!opts.allowed(f)) continue } // the event search's toggles decide (types, user / friend events)
    else if (opts.mode === 'events' && !(p.kind === 'event' && p.starts_at)) continue // Events: only real events with a date, never places or classes
    if (type && typeOf(p) !== type) continue // a type picked: only pins of that type
    const title = fold(p.title), rest = fold(`${p.venue_name || ''} ${p.lead || ''} ${p.address || ''} ${p.district || ''} ${(p.categories || []).map(categoryLabel).join(' ')} ${typeLabel(typeOf(p))}`)
    const a = whatScore(p, u.categories, title); if (!a) continue
    const b = whenScore(p, u.when, u.evening, u.categories, now); if (!b) continue
    const c = whereScore(f, where); if (!c) continue
    const t = termScore(u.terms, title, rest)
    if (u.terms.length && !structured && !t) continue // plain text search: must mention a word
    const exact = a === 2 && b === 2 && c === 2
    const score = a + b + c + t + (p.starts_at ? 0.5 : 0)
    scored.push({ f, exact, score, start: p.starts_at ? parse(p.starts_at).getTime() : Infinity })
  }
  scored.sort((x, y) => Number(y.exact) - Number(x.exact) || y.score - x.score || x.start - y.start)
  const results = scored.slice(0, MAX_RESULTS)
  const summary = [
    type && typeLabel(type), ...u.categories.map(categoryLabel), whenLabel(u.when), u.area?.name, ...u.terms,
  ].filter(Boolean).join(' · ')
  return {
    results: results.map((r) => r.f),
    exact: results.filter((r) => r.exact).length,
    understood: u,
    summary: summary || query,
    area: u.area?.feature || null,
  }
}
