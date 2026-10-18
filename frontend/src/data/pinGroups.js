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
  { id: 'food', param: 'pinFood', label: 'Food', emoji: '🍴' }, // food markets (restaurants once a source has them)
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
  if (has(FOOD) || FOOD_PLACES.includes(p.venue_type)) return 'food'
  if (has(MUSIC)) return 'music'
  if (p.kind === 'class' || p.venue_type === 'pitch' || has(CLUBS)) return 'clubs'
  if (p.kind === 'place') return 'sights'
  return 'events'
}

/** The same features with `pin_group` set, for the map's filter. */
export function withPinGroups(fc) {
  if (!fc) return fc
  return { ...fc, features: fc.features.map((f) => ({ ...f, properties: { ...f.properties, pin_group: pinGroup(f.properties) } })) }
}

/** Option ids that are switched on in the config. */
export const enabledPinGroups = (v) => PIN_GROUPS.filter((g) => v[g.param] !== false).map((g) => g.id)
