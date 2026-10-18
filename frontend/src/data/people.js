/**
 * People on the map ("share my area", backend/app/routers/people.py): everyone sharing roughly where they
 * are, and my own switch. One small store so the toolbar's People box and the map pins agree.
 */
import { useSyncExternalStore } from 'react'
import { fetchMyArea, fetchSharingPeople, isLoggedIn, setMyArea } from './api'

let state = { people: [], mine: null } // mine: { share, lat, lng } once loaded, null when logged out
const listeners = new Set()
const emit = (patch) => { state = { ...state, ...patch }; listeners.forEach((fn) => fn()) }
const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }
const get = () => state

export const usePeople = () => useSyncExternalStore(subscribe, get, get)

export async function refreshPeople() {
  const [people, mine] = await Promise.all([
    fetchSharingPeople().catch(() => state.people),
    isLoggedIn() ? fetchMyArea().catch(() => state.mine) : null,
  ])
  emit({ people: Array.isArray(people) ? people : [], mine })
}

/** Switch "Share my area" on (at lngLat) or off. Throws LoginRequired when logged out. */
export async function shareArea(on, lngLat) {
  const mine = await setMyArea(on, lngLat)
  emit({ mine })
  refreshPeople()
  return mine
}
