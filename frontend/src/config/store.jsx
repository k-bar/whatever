import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { DEFAULTS, PARAMS } from './schema'

const KEY = 'warszawa-live.ui.v2'
const Ctx = createContext(null)

// only settings that still exist: a removed param is dropped instead of being carried along forever
const known = (o) => Object.fromEntries(Object.entries(o || {}).filter(([id]) => PARAMS[id]))

function readLocal(key = KEY) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? known(JSON.parse(raw)) : {}
  } catch {
    return {}
  }
}

// What a visitor picks on the map itself (dark mode, time window, the pin and people switches) is remembered
// in every build, not only through the editor's Save (which is a dev tool).
const PREFS_KEY = 'syrenka.prefs.v1'
const USER_PREFS = new Set(['darkMode', 'timeWindow', 'busyAreas', 'showPeople', 'openNow', 'showToilets', 'showAed', 'showWalks',
  'showStations', 'showEvents', 'showPlaces', 'showPitches', 'showInvites', 'starredDefault'])
const isPref = (id) => USER_PREFS.has(id) || (/^pin[A-Z]/.test(id) && id !== 'pinIcons' && PARAMS[id]?.type === 'toggle') // the pin box's switches
const prefsOf = (v) => Object.fromEntries(Object.entries(v).filter(([id]) => isPref(id)))

/** Push every config value onto <html> as CSS variables + data attributes. */
export function applyConfig(v) {
  const root = document.documentElement
  for (const [id, value] of Object.entries(v)) {
    const p = PARAMS[id]
    if (!p) continue
    if (p.type === 'range') root.style.setProperty(`--${id}`, `${value}${p.unit && p.unit !== '×' ? p.unit : ''}`)
    else if (p.type === 'color') root.style.setProperty(`--${id}`, value)
    else if (p.type === 'toggle') root.dataset[id] = value ? 'on' : 'off'
    else root.dataset[id] = String(value)
  }
  // derived
  root.style.setProperty('--titleFontFamily', `'${v.titleFont}', system-ui, sans-serif`)
  root.style.setProperty('--bodyFontFamily', `'${v.bodyFont}', system-ui, sans-serif`)
  root.style.setProperty('--anim', `${(1 / (v.animSpeed || 1)).toFixed(2)}`)
  root.dataset.theme = v.darkMode ? 'dark' : 'light'
  root.style.setProperty('--surface-rgb', v.darkMode ? '24, 28, 35' : '255, 255, 255')
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', v.darkMode ? '#0e1116' : '#f4f1ea')
}

export function ConfigProvider({ children }) {
  const [saved, setSaved] = useState(() => ({ ...DEFAULTS, ...readLocal(), ...readLocal(PREFS_KEY) }))
  const [values, setValues] = useState(saved)
  const [status, setStatus] = useState('idle') // idle | saving | saved | error

  useEffect(() => { applyConfig(values) }, [values])
  useEffect(() => { try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefsOf(values))) } catch { /* private mode */ } }, [values])

  // undo / redo history: consecutive edits of the same param within 700ms are coalesced (slider drags)
  const past = useRef([]), future = useRef([]), lastEdit = useRef({ id: null, t: 0 })
  const [histN, setHistN] = useState(0)
  const bump = () => setHistN((n) => n + 1)
  const set = useCallback((id, value) => setValues((v) => {
    const now = Date.now()
    if (!(lastEdit.current.id === id && now - lastEdit.current.t < 700)) past.current.push(v)
    if (past.current.length > 80) past.current.shift()
    lastEdit.current = { id, t: now }
    future.current = []
    bump()
    return { ...v, [id]: value }
  }), [])
  const setMany = useCallback((patch) => setValues((v) => { past.current.push(v); future.current = []; lastEdit.current = { id: null, t: 0 }; bump(); return { ...v, ...patch } }), [])
  const undo = useCallback(() => setValues((v) => { const p = past.current.pop(); if (!p) return v; future.current.push(v); lastEdit.current = { id: null, t: 0 }; bump(); return p }), [])
  const redo = useCallback(() => setValues((v) => { const f = future.current.pop(); if (!f) return v; past.current.push(v); lastEdit.current = { id: null, t: 0 }; bump(); return f }), [])
  const canUndo = past.current.length > 0, canRedo = future.current.length > 0
  void histN

  const save = useCallback(async () => {
    setStatus('saving')
    // only what differs from the defaults: a default changed later (a new feature switched on) still reaches this browser
    try { localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(Object.entries(values).filter(([id, val]) => val !== DEFAULTS[id])))) } catch { /* private mode */ }
    setSaved(values)
    setStatus('saved') // this browser only: the backend has no settings endpoint
    setTimeout(() => setStatus('idle'), 1800)
  }, [values])

  const reset = useCallback(() => setValues((v) => { past.current.push(v); future.current = []; bump(); return { ...DEFAULTS } }), [])
  const revert = useCallback(() => setValues(saved), [saved])
  const dirty = useMemo(() => JSON.stringify(values) !== JSON.stringify(saved), [values, saved])

  const api = useMemo(() => ({ values, set, setMany, save, reset, revert, dirty, status, undo, redo, canUndo, canRedo }), [values, set, setMany, save, reset, revert, dirty, status, undo, redo, canUndo, canRedo])
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>
}

export const useConfig = () => useContext(Ctx)

/** Framer-motion spring derived from the Motion section. */
export function useSpring(overrides = {}) {
  const { values } = useConfig()
  const speed = values.animSpeed || 1
  const bounce = values.reduceMotion ? 0 : values.bounce
  return { type: 'spring', stiffness: 420 * speed, damping: 34 - bounce * 40, mass: 0.9, ...overrides }
}
