import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { DEFAULTS, PARAMS } from './schema'
import { saveSettings, loadSettings } from '../data/api'

const KEY = 'warszawa-live.ui.v2'
const Ctx = createContext(null)

function readLocal() {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

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
  const tint = { neutral: v.darkMode ? '24, 28, 35' : '255, 255, 255', warm: v.darkMode ? '34, 28, 24' : '255, 249, 240', cool: v.darkMode ? '20, 28, 40' : '240, 247, 255', accent: hexToRgb(v.accent, v.darkMode) }[v.glassTint] || '255,255,255'
  root.style.setProperty('--surface-rgb', tint)
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', v.darkMode ? '#0e1116' : '#f4f1ea')
}

export function ConfigProvider({ children }) {
  const [saved, setSaved] = useState(() => ({ ...DEFAULTS, ...readLocal() }))
  const [values, setValues] = useState(saved)
  const [status, setStatus] = useState('idle') // idle | saving | saved | error

  useEffect(() => { applyConfig(values) }, [values])

  // Settings saved on the backend (if it is up) win over localStorage.
  useEffect(() => {
    loadSettings().then((remote) => {
      if (remote && Object.keys(remote).length) {
        const merged = { ...DEFAULTS, ...remote }
        setSaved(merged)
        setValues(merged)
      }
    })
  }, [])

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
    localStorage.setItem(KEY, JSON.stringify(values))
    setSaved(values)
    const ok = await saveSettings(values)
    setStatus(ok ? 'saved' : 'local')
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

function hexToRgb(hex, dark) {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  const mix = (c, to) => Math.round(c * 0.25 + to * 0.75)
  return dark ? `${mix(r, 24)}, ${mix(g, 28)}, ${mix(b, 35)}` : `${mix(r, 255)}, ${mix(g, 255)}, ${mix(b, 255)}`
}
