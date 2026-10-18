/**
 * What the map shows, when the event search is in charge.
 *
 * Two things can decide the map: the toolbar pin menu ("Show on the map", the default) and the event
 * search's toggles. Whichever was used last wins: opening the event search hands the map to it (and
 * blanks it: every category off, a clean canvas for a precise search); touching the pin menu hands it back.
 *
 * In the event search: category toggles (the types in data/types.js; a pin counts under its own type and
 * under the types its tags mean, see typesOf), an all-on / all-off switch, "User events" (made by people
 * on Syrenka) and "Friend events" (made by your friends), and When / Where, which thin the dots live.
 * Remembered in the browser, so the map looks the same after a reload.
 */
import { useSyncExternalStore } from 'react'
import { SEARCH_TYPES, TYPES, typesOf } from './types'
import { fetchFriends, fetchMe, onAuthChange } from './api'

const KEY = 'syrenka.mapfilter.v1'
const EMPTY = { source: 'pins', types: [], users: false, friends: false, when: null, where: null }

const revive = (s) => (s?.when ? { ...s, when: { ...s.when, from: new Date(s.when.from), to: new Date(s.when.to) } } : s)
let state = (() => { try { return { ...EMPTY, ...revive(JSON.parse(localStorage.getItem(KEY) || 'null')) } } catch { return { ...EMPTY } } })()
const subs = new Set()

function write(patch) {
  state = { ...state, ...patch }
  try { localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* private mode */ }
  subs.forEach((fn) => fn())
}

export const useMapFilter = () => useSyncExternalStore((fn) => { subs.add(fn); return () => subs.delete(fn) }, () => state)
export const getMapFilter = () => state

/** Opening the event search: it takes over the map and starts from a blank canvas. */
export const openSearchCanvas = () => write({ source: 'search', types: [] })
/** The pin menu was used: it decides the map again. */
export const handToPinMenu = () => { if (state.source !== 'pins') write({ source: 'pins' }) }
export const toggleType = (id) => write({ source: 'search', types: state.types.includes(id) ? state.types.filter((t) => t !== id) : [...state.types, id] })
/** A whole group (Sights, Music, ...) on or off. */
export const setGroup = (group, on) => {
  const ids = SEARCH_TYPES.filter((id) => TYPES[id].group === group)
  write({ source: 'search', types: on ? [...new Set([...state.types, ...ids])] : state.types.filter((t) => !ids.includes(t)) })
}
export const setAllTypes = (on) => write({ source: 'search', types: on ? [...SEARCH_TYPES] : [] })
export const setTypes = (types) => write({ source: 'search', types: [...new Set(types)] })
export const setUsersOnly = (on) => write({ source: 'search', users: on })
export const setFriendsOnly = (on) => write({ source: 'search', friends: on })
export const setWhen = (when) => write({ source: 'search', when })
export const setWhere = (where) => write({ source: 'search', where })

export const allTypesOn = (s = state) => SEARCH_TYPES.every((id) => s.types.includes(id))
export const groupState = (group, s = state) => {
  const ids = SEARCH_TYPES.filter((id) => TYPES[id].group === group)
  const on = ids.filter((id) => s.types.includes(id)).length
  return on === 0 ? 'off' : on === ids.length ? 'on' : 'some'
}

// ---------- user and friend events ----------

/** Made by someone on Syrenka ("+ Create event"), not taken from a city or ticket source. */
export const isUserEvent = (p) => Boolean(p.source === 'syrenka-users' || p.is_public_invite || p.audience)
const hostOf = (p) => p.host?.id ?? p.host_user_id ?? null

let friendIds = new Set()
const friendSubs = new Set()
async function loadFriends() {
  const me = await fetchMe().catch(() => null)
  const list = me ? await fetchFriends(me.id).catch(() => []) : []
  friendIds = new Set(list.map((u) => u.id))
  friendSubs.forEach((fn) => fn())
}
loadFriends()
onAuthChange(loadFriends)
export const useFriendIds = () => useSyncExternalStore((fn) => { friendSubs.add(fn); return () => friendSubs.delete(fn) }, () => friendIds)
export const isFriendEvent = (p, ids = friendIds) => isUserEvent(p) && ids.has(hostOf(p))

/** Does a pin pass the toggles (types, user / friend events)? When and Where are checked separately. */
export function passesToggles(p, s = state, ids = friendIds) {
  if (s.friends && !isFriendEvent(p, ids)) return false
  if (s.users && !isUserEvent(p)) return false
  if (!s.types.length) return s.users || s.friends // only "User events" on: all of them
  const on = new Set(s.types)
  return typesOf(p).some((t) => on.has(t))
}
