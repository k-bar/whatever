import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchFavourites, isLoggedIn, onAuthChange, saveFavourites } from '../data/api'

// Event/venue IDs (events.id) as numbers. v1 held made-up IDs from the old sample data, so it's ignored.
const KEY = 'syrenka.favourites.v2'
const SAVE_DELAY_MS = 600

const readLocal = () => {
  try { return new Set((JSON.parse(localStorage.getItem(KEY) || '[]')).map(Number).filter(Number.isFinite)) } catch { return new Set() }
}

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
  const sync = useCallback(() => {
    synced.current = false
    if (!isLoggedIn()) return
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
    const n = new Set(s), key = Number(id)
    n.has(key) ? n.delete(key) : n.add(key)
    return n
  }), [])
  const has = useCallback((id) => ids.has(Number(id)), [ids])
  return { ids, toggle, has }
}
