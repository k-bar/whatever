import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchFavourites, isLoggedIn, onAuthChange, saveFavourites } from '../data/api'

// Event/venue IDs (events.id) as numbers. v1 held made-up IDs from the old sample data, so it's ignored.
const KEY = 'syrenka.favourites.v2'
const GUEST_KEY = 'syrenka.favourites.guest' // this browser's own stars, put back on log out
const SAVE_DELAY_MS = 600

const readLocal = (key = KEY) => {
  try { return new Set((JSON.parse(localStorage.getItem(key) || '[]')).map(Number).filter(Number.isFinite)) } catch { return new Set() }
}
// Only real events / places (numeric ids) can be starred: a walk ("walk-3") or a private event ("ue-12")
// would become NaN, and a Set treats every NaN as one value (star one, all show starred; the API rejects it).
const starable = (id) => Number.isFinite(Number(id)) && id !== '' && id != null

/**
 * Favourite spots.
 * - Not logged in: kept in this browser only (localStorage), nothing goes to the server.
 * - Logged in: also saved with the account in PostgreSQL (users.favourite_ids), so they follow you to
 *   other devices. Logging in merges what this browser starred into the account.
 */
export function useFavourites() {
  const [ids, setIds] = useState(readLocal)
  const synced = useRef(false) // true once the logged-in account's list has been read and merged
  const timer = useRef(null)

  // read the account's list (if logged in) and merge it with this browser's stars
  const wasIn = useRef(isLoggedIn())
  const sync = useCallback(() => {
    const before = wasIn.current, now = isLoggedIn()
    wasIn.current = now
    synced.current = false
    if (!now) {
      // logged out: the account's stars leave with it (the next person on this browser must not inherit them)
      if (before) setIds(readLocal(GUEST_KEY))
      return
    }
    // logging in: remember this browser's own stars first, to put back on log out
    if (!before) try { localStorage.setItem(GUEST_KEY, localStorage.getItem(KEY) || '[]') } catch { /* private mode */ }
    fetchFavourites().then((saved) => {
      synced.current = isLoggedIn()
      // a new Set either way, so the merged list is saved back to the account
      setIds((local) => new Set([...(saved || []), ...local]))
    })
  }, [])

  useEffect(() => { sync(); return onAuthChange(sync) }, [sync])

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify([...ids])) } catch { /* private mode */ }
    if (!synced.current || !isLoggedIn()) return // logged out: browser only
    clearTimeout(timer.current)
    timer.current = setTimeout(() => saveFavourites([...ids]), SAVE_DELAY_MS)
  }, [ids])

  const toggle = useCallback((id) => setIds((s) => {
    if (!starable(id)) return s
    const n = new Set(s), key = Number(id)
    n.has(key) ? n.delete(key) : n.add(key)
    return n
  }), [])
  const has = useCallback((id) => starable(id) && ids.has(Number(id)), [ids])
  return { ids, toggle, has }
}
