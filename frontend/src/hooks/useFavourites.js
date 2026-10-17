import { useCallback, useEffect, useState } from 'react'

const KEY = 'warszawa-live.favourites.v1'
// Seeded so the "starred places" layer has something to show on first run.
const SEED = ['node/327614614', 'node/264588401', 'node/263810164', 'invite/0', 'invite/3']

export function useFavourites() {
  const [ids, setIds] = useState(() => {
    try {
      const raw = localStorage.getItem(KEY)
      return new Set(raw ? JSON.parse(raw) : SEED)
    } catch {
      return new Set(SEED)
    }
  })
  useEffect(() => { localStorage.setItem(KEY, JSON.stringify([...ids])) }, [ids])
  const toggle = useCallback((id) => setIds((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n }), [])
  const has = useCallback((id) => ids.has(id), [ids])
  return { ids, toggle, has }
}
