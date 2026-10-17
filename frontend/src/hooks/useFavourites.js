import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchFavourites, saveFavourites } from '../data/api'

// Event/venue IDs (events.id) as numbers. v1 held made-up IDs from the old sample data, so it's ignored.
const KEY = 'syrenka.favourites.v2'
const SAVE_DELAY_MS = 600

const readLocal = () => {
  try { return new Set((JSON.parse(localStorage.getItem(KEY) || '[]')).map(Number).filter(Number.isFinite)) } catch { return new Set() }
}

/**
 * Favourite spots: kept in this browser and saved with the account in PostgreSQL (users.favourite_ids),
 * so they follow you to other devices. On load the account's list and this browser's are merged.
 */
export function useFavourites() {
  const [ids, setIds] = useState(readLocal)
  const synced = useRef(false)
  const timer = useRef(null)

  useEffect(() => {
    fetchFavourites().then((saved) => {
      if (saved?.length) setIds((local) => new Set([...saved, ...local]))
      synced.current = true
    })
  }, [])

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify([...ids])) } catch { /* private mode */ }
    if (!synced.current) return // don't overwrite the account before its list has been read
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
