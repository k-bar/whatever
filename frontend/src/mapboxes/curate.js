/**
 * Map box curation: decide what the small info box shows for a clicked feature.
 * Returns an ordered list of blocks. backend/mapboxes/curate.py is the server-side twin;
 * when it answers (fetchMapbox), its `blocks` replace these.
 *
 * Block types rendered by <MapBox>: posters, hours, pitch, live, social, text, facts, tickets
 */
import { categoryLabel } from '../data/categories'

const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']

export function fmtWhen(iso) {
  if (!iso) return null
  const d = new Date(String(iso).replace(/([+-]\d{2})$/, '$1:00'))
  if (Number.isNaN(d.getTime())) return iso
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1)
  const day = sameDay ? 'Today' : d.toDateString() === tomorrow.toDateString() ? 'Tomorrow'
    : d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  const time = d.getHours() + d.getMinutes() === 0 ? '' : d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  return time ? `${day} · ${time}` : day
}

export function curate(feature, ctx = {}) {
  const p = feature.properties
  const blocks = []
  const badges = (p.categories || []).slice(0, 2).map(categoryLabel)
  if (p.is_public_invite) badges.unshift('Public invite')
  if (p.source === 'warsaw_open_data') badges.push('City data')

  // ---- events ---------------------------------------------------------------------------------
  if (p.kind === 'event') {
    blocks.push({ type: 'facts', items: [
      p.starts_at && { icon: 'clock', text: fmtWhen(p.starts_at) },
      p.venue_name && { icon: 'pin', text: p.venue_name },
      p.district && { icon: 'map', text: p.district },
      p.is_recurring && { icon: 'repeat', text: 'Recurring' },
    ].filter(Boolean) })
    if (p.is_public_invite) {
      blocks.push({ type: 'social', host: p.host?.display_name, attendees: p.attendees, wanting: p.wanting_company,
        seats: p.seats_left, capacity: p.capacity, cta: 'Ask to join' })
    } else if (p.attendees || p.wanting_company) {
      blocks.push({ type: 'social', attendees: p.attendees, wanting: p.wanting_company, cta: "I'm going, come with me" })
    } else {
      blocks.push({ type: 'social', attendees: 0, wanting: 0, cta: "I'm going, come with me" })
    }
    if (p.lead) blocks.push({ type: 'text', text: p.lead })
    return { title: p.title, subtitle: p.venue_name || p.address, badges, image: p.image_url, blocks, url: p.url }
  }

  // ---- places ---------------------------------------------------------------------------------
  if (p.venue_type === 'pitch') {
    const today = DAYS[new Date().getDay()]
    blocks.push({ type: 'pitch', equipment: p.equipment || [], surface: p.surface, today: p.opening_hours?.[today],
      hours: p.opening_hours || {}, approx: p.approx_location })
    blocks.push({ type: 'social', attendees: 0, wanting: 0, cta: 'Find players for a game' })
    return { title: p.venue_name || p.title, subtitle: `${p.address}, ${p.district}`, badges: ['Open pitch', 'City data'], blocks }
  }

  const upcoming = p.upcoming || []
  if (upcoming.length) blocks.push({ type: 'posters', items: upcoming })
  if (p.venue_type === 'nightclub') {
    blocks.push({ type: 'live', text: ctx.busy ? `${ctx.busy} busy right now` : 'Quiet now, fills up after 23:00', level: ctx.busy ? 'hot' : 'calm' })
  }
  if (p.opening_hours && typeof p.opening_hours === 'string') blocks.push({ type: 'hours', text: p.opening_hours })
  const facts = [
    p.address && { icon: 'pin', text: p.address },
    p.capacity && { icon: 'users', text: `Capacity ${p.capacity}` },
    p.wheelchair && { icon: 'access', text: `Wheelchair: ${p.wheelchair}` },
    p.phone && { icon: 'phone', text: p.phone },
  ].filter(Boolean)
  if (facts.length) blocks.push({ type: 'facts', items: facts })
  if (!upcoming.length) blocks.push({ type: 'text', muted: true, text: 'No ticketed shows found for this venue in the next weeks. Starred by 12 people.' })
  return {
    title: p.title, subtitle: p.venue_type ? p.venue_type.replace('_', ' ') : null,
    badges: [p.venue_type?.replace('_', ' '), 'OpenStreetMap'].filter(Boolean), image: p.image_url, blocks, url: p.url,
  }
}
