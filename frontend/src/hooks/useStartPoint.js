import { useSyncExternalStore } from 'react'
import { loadStartPoint, saveStartPoint } from '../data/api'

// The user's chosen starting point (Profile → Set my location to), shared app-wide. null = IP guess.
let current = loadStartPoint()
const subs = new Set()

export function setStartPoint(point) {
  current = point
  saveStartPoint(point)
  subs.forEach((fn) => fn())
}

export const useStartPoint = () => useSyncExternalStore((fn) => { subs.add(fn); return () => subs.delete(fn) }, () => current)
