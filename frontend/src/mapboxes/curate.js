import { locale, translate } from '../i18n'
/**
 * Map box curation: decide what the small info box shows for a clicked feature.
 * Returns an ordered list of blocks. Curation is client-side only: the backend has no /mapboxes endpoint.
 *
 * Block types rendered by <MapBox>: posters, hours, week, pitch, live, social, text, facts, tickets
 */
import { AUDIENCES, EVENT_TYPES, categoryLabel } from '../data/categories'
import { weekHours } from '../data/hours'

const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']

export function fmtWhen(iso) {
  if (!iso) return null
  const d = new Date(String(iso).replace(/([+-]\d{2})$/, '$1:00'))
  if (Number.isNaN(d.getTime())) return iso
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1)
  const day = sameDay ? translate('Today') : d.toDateString() === tomorrow.toDateString() ? translate('Tomorrow')
    : d.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
  const time = d.getHours() + d.getMinutes() === 0 ? '' : d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
  return time ? `${day} · ${time}` : day
}

/** Like fmtWhen(starts_at), but something already running shows when it ends: "Now · until 22:00" / "On until Sun 30 Nov". */
export function fmtWhenFor(p) {
  if (!p?.starts_at) return null
  const parse = (iso) => new Date(String(iso).replace(/([+-]\d{2})$/, '$1:00'))
  const now = new Date(), s = parse(p.starts_at), e = p.ends_at && parse(p.ends_at)
  if (e && s < now && e >= now) {
    if (e.toDateString() === now.toDateString()) return translate('Now · until {time}', { time: e.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' }) })
    return translate('On until {date}', { date: e.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' }) })
  }
  return fmtWhen(p.starts_at)
}

export function curate(feature, ctx = {}) {
  const p = feature.properties
  const blocks = []
  const badges = (p.categories || []).slice(0, 2).map(categoryLabel)
  if (p.is_public_invite) badges.unshift('Public invite')
  if (p.source?.startsWith('warsaw_')) badges.push('City data') // warsaw_events, warsaw_sport, ... (GET /sources)
  if (p.source === 'kupbilecik') badges.push('Tickets')

  // ---- "In the city" layers: toilets, defibrillators, walking routes (components/cityLayers.js) ----
  const cats = p.categories || []
  if (cats.includes('toilets')) {
    const today = p.opening_hours?.[DAYS[new Date().getDay()]]
    blocks.push({ type: 'facts', items: [
      p.address && { icon: 'pin', text: p.address },
      { icon: 'clock', text: /^0?0:00-24:00$/.test(today || '') ? translate('Open 24 hours') : today ? `${translate('Today')} ${today.replace('-', '–')}` : translate(p.opening_hours ? 'Closed today' : 'Opening hours unknown') },
      p.district && { icon: 'map', text: p.district },
    ].filter(Boolean) })
    return { title: translate('Public toilet'), subtitle: p.venue_name, badges: [translate('Toilets'), translate('City data')], blocks }
  }
  if (cats.includes('aed')) {
    blocks.push({ type: 'facts', items: [p.address && { icon: 'pin', text: p.address }, p.district && { icon: 'map', text: p.district }].filter(Boolean) })
    blocks.push({ type: 'text', text: translate('In a cardiac arrest: call 112, start CPR and send someone for the AED. It talks you through every step.') })
    return { title: translate('Defibrillator (AED)'), subtitle: p.venue_name, badges: ['AED', translate('City data')], blocks }
  }
  if (cats.includes('transit')) { // metro and bus stations (OpenStreetMap)
    blocks.push({ type: 'facts', items: [p.lead && { icon: 'map', text: p.lead }, p.district && { icon: 'pin', text: p.district }].filter(Boolean) })
    return { title: p.title, subtitle: null, badges: ['OpenStreetMap'], blocks, url: p.url }
  }
  if (p.kind === 'walk') {
    const stops = (p.points || []).map((s) => s.name)
    const hours = (p.length_km || 0) / 4
    blocks.push({ type: 'facts', items: [
      p.length_km && { icon: 'map', text: `${p.length_km.toFixed(1)} km` },
      p.length_km && { icon: 'clock', text: translate('about {h} h on foot, without stops', { h: hours < 1 ? hours.toFixed(1) : Math.round(hours * 2) / 2 }) },
      stops.length && { icon: 'pin', text: translate('{n} stops, from {first}', { n: stops.length, first: stops[0] }) },
    ].filter(Boolean) })
    if (p.description) blocks.push({ type: 'text', text: p.description })
    if (stops.length) blocks.push({ type: 'text', muted: true, text: stops.join(' · ') })
    return { title: p.title, subtitle: translate('Walking route'), badges: [translate('Walking route'), translate('City data')], blocks }
  }

  // ---- events people made with "+ Create event" (backend/app/userevents) -----------------------
  if (p.audience) {
    const until = p.ends_at && new Date(p.ends_at).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
    blocks.push({ type: 'facts', items: [
      p.starts_at && { icon: 'clock', text: until ? `${fmtWhen(p.starts_at)} – ${until}` : fmtWhen(p.starts_at) },
      (p.venue_name || p.address) && { icon: 'pin', text: [p.venue_name, p.address].filter(Boolean).join(' · ') },
    ].filter(Boolean) })
    blocks.push({ type: 'social', host: p.host?.display_name, attendees: p.attendees, wanting: p.wanting_company,
      cta: translate(p.audience === 'public' ? 'Join' : p.audience === 'public_confirm' ? 'Ask to join' : "I'm going") })
    if (p.lead) blocks.push({ type: 'text', text: p.lead })
    const type = EVENT_TYPES[p.event_type]
    return { title: p.title, subtitle: p.subtitle || p.venue_name || p.address, image: p.image_url, blocks,
      badges: [type && translate(type.label), translate(AUDIENCES[p.audience]?.label || p.audience)].filter(Boolean) }
  }

  // ---- events ---------------------------------------------------------------------------------
  if (p.kind === 'event') {
    blocks.push({ type: 'facts', items: [
      p.starts_at && { icon: 'clock', text: fmtWhen(p.starts_at) },
      p.venue_name && { icon: 'pin', text: p.venue_name },
      p.district && { icon: 'map', text: p.district },
      p.is_recurring && { icon: 'repeat', text: translate('Recurring') },
    ].filter(Boolean) })
    if (p.is_public_invite) {
      blocks.push({ type: 'social', host: p.host?.display_name, attendees: p.attendees, wanting: p.wanting_company,
        seats: p.seats_left, capacity: p.capacity, cta: translate('Ask to join') })
    } else if (p.attendees || p.wanting_company) {
      blocks.push({ type: 'social', attendees: p.attendees, wanting: p.wanting_company, cta: translate("I'm going, come with me") })
    } else {
      blocks.push({ type: 'social', attendees: 0, wanting: 0, cta: translate("I'm going, come with me") })
    }
    if (p.lead) blocks.push({ type: 'text', text: p.lead })
    return { title: p.title, subtitle: p.venue_name || p.address, badges, image: p.image_url, blocks, url: p.url }
  }

  // ---- places ---------------------------------------------------------------------------------
  if (p.venue_type === 'pitch' || p.source === 'warsaw_pitches') {
    const today = DAYS[new Date().getDay()]
    blocks.push({ type: 'pitch', equipment: p.equipment || [], surface: p.surface, today: p.opening_hours?.[today],
      hours: p.opening_hours || {}, approx: p.approx_location })
    blocks.push({ type: 'social', attendees: 0, wanting: 0, cta: 'Find players for a game' })
    return { title: p.venue_name || p.title, subtitle: `${p.address}, ${p.district}`, badges: ['Open pitch', 'City data'], blocks }
  }

  const upcoming = p.upcoming || []
  if (upcoming.length) blocks.push({ type: 'posters', items: upcoming })
  if (p.opening_hours && typeof p.opening_hours === 'string') blocks.push({ type: 'hours', text: p.opening_hours })
  // per-day hours (restaurants, cafes, bars, venues from OpenStreetMap): open now?, today, the week
  const week = weekHours(p.opening_hours)
  if (week) blocks.push({ type: 'week', ...week })
  const facts = [
    p.address && { icon: 'pin', text: p.address },
    p.capacity && { icon: 'users', text: `Capacity ${p.capacity}` },
    p.wheelchair && { icon: 'access', text: `Wheelchair: ${p.wheelchair}` },
    p.phone && { icon: 'phone', text: p.phone },
  ].filter(Boolean)
  if (facts.length) blocks.push({ type: 'facts', items: facts })
  const eatery = p.source === 'osm_restaurants' // Kamil's restaurants, cafes, bars, pubs: no shows to look for
  if (!upcoming.length && !eatery) blocks.push({ type: 'text', muted: true, text: 'No ticketed shows found for this venue in the next weeks.' })
  return {
    title: p.title, subtitle: eatery ? p.lead : p.venue_type ? p.venue_type.replace('_', ' ') : null,
    badges: [p.venue_type?.replace('_', ' '), 'OpenStreetMap'].filter(Boolean), image: p.image_url, blocks, url: p.url,
  }
}
