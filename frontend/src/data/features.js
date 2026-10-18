/**
 * Pins and time, in one place: which date of an event the map shows, and whether it falls in the
 * toolbar's time window. The map filter, its JS twin (counts), the event search and the boxes all use these.
 *
 * GET /events answers one feature per *date* (occurrence): a weekly class comes back once per week, up to
 * 19 identical pins on one spot, each opening a different date. onePinPerEvent() keeps one pin per event:
 * its first date inside the time window (else its next date), with how many dates it has.
 *
 * Times are compared as numbers (ms), never as ISO text: the API's offsets ("+00:00", "+01:00") and the
 * browser's own "Z" strings don't sort together.
 */

const DEFAULT_LENGTH = 2 * 3600e3 // an event without an end is taken to last two hours

/** "2026-10-18T19:00:00+02" (no minutes in the offset) parses too. */
export const toDate = (iso) => new Date(String(iso).replace(/([+-]\d{2})$/, '$1:00'))
export const toMs = (iso) => (iso ? toDate(iso).getTime() : NaN)
export const startMs = (p) => toMs(p?.starts_at)
export const endMs = (p) => (p?.ends_at ? toMs(p.ends_at) : startMs(p) + DEFAULT_LENGTH)

/** The toolbar's time window as [from, to] in ms (device time), or null for "any time". */
export function windowRange(window, now = new Date()) {
  const start = new Date(now)
  const end = new Date(now)
  if (window === 'today') end.setHours(23, 59, 59, 999)
  else if (window === 'weekend') {
    const day = now.getDay() // 0 Sun .. 6 Sat
    if (day !== 0 && day !== 6) { start.setDate(now.getDate() + (6 - day)); start.setHours(0, 0, 0, 0) } // Saturday 00:00
    end.setDate(now.getDate() + (day === 0 ? 0 : 7 - day)); end.setHours(23, 59, 59, 999) // to Sunday night
  } else if (window === 'week') end.setDate(now.getDate() + 7)
  else if (window === 'month') end.setDate(now.getDate() + 30)
  else return null
  return [start.getTime(), end.getTime()]
}

/** Does this pin happen in [from, to]? Overlap, so an exhibition that opened last month is still "today". Undated places: always. */
export function inWindow(p, range) {
  if (!range || !p?.starts_at) return true
  const s = startMs(p)
  return s <= range[1] && endMs(p) >= range[0]
}

/** The same features with one pin per event: its first date in `range`, else its next one, else its last. */
export function onePinPerEvent(fc, range, now = Date.now()) {
  if (!fc) return fc
  const groups = new Map()
  const out = []
  for (const f of fc.features) {
    const id = f.properties.event_id
    if (id == null || !f.properties.starts_at) { out.push(f); continue }
    let g = groups.get(id)
    if (!g) { g = []; groups.set(id, g); out.push(g) } // keep the event where it first appeared
    g.push(f)
  }
  return {
    ...fc,
    features: out.map((g) => {
      if (!Array.isArray(g)) return g
      if (g.length === 1) return g[0]
      g.sort((a, b) => startMs(a.properties) - startMs(b.properties))
      const pick = g.find((f) => inWindow(f.properties, range) && endMs(f.properties) >= now)
        || g.find((f) => endMs(f.properties) >= now) || g[g.length - 1]
      return { ...pick, properties: { ...pick.properties, dates: g.length } }
    }),
  }
}
