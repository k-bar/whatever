import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { DEFAULTS, PARAMS } from './schema'
import { saveSettings, loadSettings } from '../data/api'

const KEY = 'warszawa-live.ui.v1'
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

  const set = useCallback((id, value) => setValues((v) => ({ ...v, [id]: value })), [])
  const setMany = useCallback((patch) => setValues((v) => ({ ...v, ...patch })), [])

  const save = useCallback(async () => {
    setStatus('saving')
    localStorage.setItem(KEY, JSON.stringify(values))
    setSaved(values)
    const ok = await saveSettings(values)
    setStatus(ok ? 'saved' : 'local')
    setTimeout(() => setStatus('idle'), 1800)
  }, [values])

  const reset = useCallback(() => setValues({ ...DEFAULTS }), [])
  const revert = useCallback(() => setValues(saved), [saved])
  const dirty = useMemo(() => JSON.stringify(values) !== JSON.stringify(saved), [values, saved])

  const api = useMemo(() => ({ values, set, setMany, save, reset, revert, dirty, status }), [values, set, setMany, save, reset, revert, dirty, status])
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
