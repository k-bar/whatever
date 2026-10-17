/**
 * "Syrenka poleca" / "Syrenka Selects": the landing page's pick of what's worth going to soon.
 *
 * An aggregation of the real events the API returns, scored and then picked for variety:
 *   score = soon × kind of event × (photo, description, big-name venue, people going) bonuses
 * Year-long "daily" listings (social services, permanent offers) and things that already ended are
 * dropped. Picking is greedy with penalties for repeating a category or a venue, so the grid reads
 * as a mix. Every pick has a poster. The top row is two normal cards (so more than one shows above
 * the fold); the two best picks become 2-wide headliners further down.
 *
 * Later: people going / "wants company" counts from our own users, and paid slots (sponsored: true),
 * which the grid already knows how to place.
 */

const DAY = 24 * 60 * 60 * 1000
const HORIZON_DAYS = 14

// how much a kind of event usually makes someone go out (sports listings are mostly regular classes)
const KIND = {
  music: 1.0, festivals: 1.0, theatre: 0.95, nightlife: 0.9, film: 0.85, exhibitions: 0.85, culture: 0.8,
  markets: 0.75, meetups: 0.7, family: 0.65, running: 0.6, yoga: 0.5, sports: 0.45, education: 0.4,
  study_buddies: 0.4, business: 0.35, health: 0.3, grzybki: 0.6, other: 0.25,
}

const BIG_VENUE = /stadion|narodow|teatr wielki|filharmoni|torwar|progresj|stodo|palladium|tama|hala koszyki|kopernik|zachęt|muzeum|łazienk|pałac kultury|plac defilad|koneser|elektrowni/i

export function pickSelects(features, { now = new Date(), count = 12, social = null } = {}) {
  const t0 = now.getTime()
  const going = social?.going || {}, joined = social?.joined || {}
  const seenTitle = new Set()
  const candidates = []
  for (const f of features || []) {
    const p = f.properties || {}
    if (p.kind !== 'event' || !p.title || !p.starts_at) continue
    const id = String(p.event_id)
    const userMade = Boolean(p.is_public_invite || p.audience) // public invitations / "+ Create event"
    const acted = Boolean(going[id] || joined[id]) // you pressed "I'm going" or "Ask to join"
    const start = Date.parse(p.starts_at), end = Date.parse(p.ends_at || p.starts_at)
    if (!Number.isFinite(start)) continue
    if (p.daily || end - start > 3 * DAY) continue // year-long listings, permanent offers
    if (end < t0 || start - t0 > HORIZON_DAYS * DAY) continue // over, or too far ahead
    if (!p.image_url) continue // posters only: Syrenka Selects is a visual pick
    const key = p.title.trim().toLowerCase()
    if (seenTitle.has(key)) continue // the same show on several dates: keep the soonest only
    seenTitle.add(key)

    const days = Math.max(0, (start - t0) / DAY)
    const cat = p.categories?.[0] || 'other'
    let score = Math.exp(-days / 5) * (KIND[cat] ?? 0.4)
    if (p.image_url) score *= 1.35
    if (p.lead) score *= 1.15
    if (BIG_VENUE.test(`${p.venue_name || ''} ${p.address || ''}`)) score *= 1.3
    score *= 1 + Math.min(1, ((p.attendees || 0) + (p.wanting_company || 0)) / 20)
    if (userMade) score *= 1.6 // people made this: the point of Syrenka Selects
    if (acted) score *= 3 // you're going / asked to join: always near the top
    candidates.push({ f, score, cat, venue: (p.venue_name || p.address || '').toLowerCase() })
  }
  candidates.sort((a, b) => b.score - a.score)

  // greedy pick with variety penalties
  const picked = [], catCount = {}, venueCount = {}
  const pool = candidates.slice(0, 200)
  while (picked.length < count && pool.length) {
    let bi = 0, bv = -1
    pool.forEach((c, i) => {
      const v = c.score * 0.6 ** (catCount[c.cat] || 0) * 0.35 ** (venueCount[c.venue] || 0)
      if (v > bv) { bv = v; bi = i }
    })
    const [c] = pool.splice(bi, 1)
    picked.push(c)
    catCount[c.cat] = (catCount[c.cat] || 0) + 1
    if (c.venue) venueCount[c.venue] = (venueCount[c.venue] || 0) + 1
  }

  // top row: the two best picks side by side; the next two best become wide headliners lower down
  const top = picked.slice(0, 2)
  const heads = picked.slice(2, 4)
  const rest = picked.slice(4)
  const order = [...top]
  if (heads[0]) order.push({ ...heads[0], wide: true })
  order.push(...rest.slice(0, 4))
  if (heads[1]) order.push({ ...heads[1], wide: true })
  order.push(...rest.slice(4))
  return order.map(({ f, wide }) => ({ feature: f, wide: !!wide, going: Boolean(going[String(f.properties.event_id)]), asked: Boolean(joined[String(f.properties.event_id)]), userMade: Boolean(f.properties.is_public_invite || f.properties.audience) }))
}

/** City images sometimes come as http://; serve them over https so the page stays secure. */
export const secureImage = (url) => (url ? url.replace(/^http:\/\//, 'https://') : url)
