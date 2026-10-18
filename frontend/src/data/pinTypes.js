/**
 * What a pin *is*, drawn as a small round badge on the map (MapView's `wl-icons` layer): one emoji and
 * colour per type. The types, and how a pin gets one, live in data/types.js (one fixed list, every pin
 * has exactly one); this file only hands them to the map.
 */
import { TYPES, typeOf } from './types'

export const PIN_TYPES = Object.fromEntries(Object.entries(TYPES).map(([id, t]) => [id, { emoji: t.emoji, color: t.color, label: t.label }]))

export const pinType = (p) => typeOf(p)
export const pinTypeOf = (p) => PIN_TYPES[pinType(p)]
