import { isOpenNow } from './hours'

/**
 * The toolbar pin button's options. Every pin belongs to exactly one group (first match wins), so turning
 * the six options on and off covers the whole map with no pin left out or counted twice.
 * Each option is a toggle in the config (`pinFriends`, `pinClubs`, ...; Interface editor -> Markers too).
 */

export const PIN_GROUPS = [
  { id: 'friends', param: 'pinFriends', label: 'New friends', emoji: '🤝' }, // posted by people on Syrenka
  { id: 'clubs', param: 'pinClubs', label: 'Social Clubs', emoji: '🏃' }, // regular classes, meetups, sport, pitches
  { id: 'events', param: 'pinEvents', label: 'Events', emoji: '📅' }, // the city calendar, tickets
  { id: 'sights', param: 'pinSights', label: 'Sights', emoji: '🏛️' }, // museums, galleries, theatres, cinemas
  { id: 'music', param: 'pinMusic', label: 'Music', emoji: '🎵' }, // concerts, clubs, festivals
  { id: 'food', param: 'pinFood', label: 'Food & drink', emoji: '🍴' }, // restaurants, cafes, bars, pubs, beer gardens, food markets
]

const MUSIC = ['music', 'nightlife', 'festivals']
const FOOD = ['food', 'markets']
const CLUBS = ['meetups', 'running', 'yoga', 'study_buddies', 'grzybki', 'sports', 'health']
const FOOD_PLACES = ['restaurant', 'cafe', 'bar', 'pub', 'fast_food', 'food_court', 'ice_cream', 'biergarten']

/** Which option a pin belongs to. */
export function pinGroup(p) {
  const cats = p.categories || []
  const has = (list) => cats.some((c) => list.includes(c))
  if (p.source === 'syrenka-users' || p.is_public_invite) return 'friends'
  // Kamil's OpenStreetMap restaurants, cafes, bars and pubs: food & drink (bars come tagged "nightlife",
  // which would otherwise put them with the music clubs)
  if (p.source === 'osm_restaurants' || has(FOOD) || FOOD_PLACES.includes(p.venue_type)) return 'food'
  // pitches and classes before music: some pitches come tagged "nightlife" too
  if (p.kind === 'class' || p.venue_type === 'pitch' || p.source === 'warsaw_pitches') return 'clubs'
  if (has(MUSIC)) return 'music'
  if (has(CLUBS)) return 'clubs'
  if (p.kind === 'place') return 'sights'
  return 'events'
}

/**
 * The same features with `pin_group` set, and `closed_now` on places whose opening hours say they're
 * closed right now (for the pin box's "Open now"), for the map's filter.
 */
export function withPinGroups(fc) {
  if (!fc) return fc
  const at = new Date()
  return { ...fc, features: fc.features.map((f) => ({ ...f, properties: { ...f.properties, pin_group: pinGroup(f.properties), closed_now: closedNow(f.properties, at) } })) }
}

/** "Open now" hides places that are closed or have no hours; dated events and classes are left alone. */
export const closedNow = (p, at = new Date()) => p.kind === 'place' && isOpenNow(p.opening_hours, at) !== true

/** Option ids that are switched on in the config. */
export const enabledPinGroups = (v) => PIN_GROUPS.filter((g) => v[g.param] !== false).map((g) => g.id)
