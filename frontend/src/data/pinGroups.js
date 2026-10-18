import { isOpenNow } from './hours'
import { typeGroup, typeOf } from './types'
import { pinType } from './pinTypes'

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

/**
 * Which pin box switch a pin belongs to: its type's group (data/types.js), except that anything a person
 * on Syrenka posted is "New friends", whatever its type. The switch overrides every type in it.
 */
export function pinGroup(p) {
  if (p.source === 'syrenka-users' || p.is_public_invite) return 'friends'
  return typeGroup(typeOf(p)) || 'events'
}

/**
 * The same features with `pin_group` set, `pin_type` (which icon: data/pinTypes.js), and `closed_now` on
 * places whose opening hours say they're closed right now (for the pin box's "Open now"), for the map.
 */
export function withPinGroups(fc) {
  if (!fc) return fc
  const at = new Date()
  return { ...fc, features: fc.features.map((f) => ({ ...f, properties: { ...f.properties, pin_group: pinGroup(f.properties), pin_type: pinType(f.properties), closed_now: closedNow(f.properties, at) } })) }
}

/** "Open now" hides places that are closed or have no hours; dated events and classes are left alone. */
export const closedNow = (p, at = new Date()) => p.kind === 'place' && isOpenNow(p.opening_hours, at) !== true

/** Option ids that are switched on in the config. */
export const enabledPinGroups = (v) => PIN_GROUPS.filter((g) => v[g.param] !== false).map((g) => g.id)
