import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { PIN_GROUPS } from '../data/pinGroups'
import { CITY_LAYERS } from './cityLayers'
import { useLang } from '../i18n'
import { Pin } from './Icons'

// one list: the busy-areas heatmap first (it used to be its own toolbar button), the kinds of pins, then the
// city's own layers (toilets / AED near your route, walking routes)
const BUSY = { id: 'busy', param: 'busyAreas', label: 'Busy areas', emoji: '🔥' }
const OPTIONS = [BUSY, ...PIN_GROUPS, ...CITY_LAYERS]

/**
 * First toolbar button: tap -> a compact box slides up (like the language picker) with a toggle per kind
 * of thing on the map. Everything is on by default; tap a row to switch it off. Tap outside the box or
 * the pin button again to close it. How many of each there are lives in Settings -> Data sources.
 */
export function PinMenu() {
  const { values, set } = useConfig()
  const { t } = useLang()
  const spring = useSpring()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div className="pinmenu" ref={ref}>
      <AnimatePresence>
        {open && (
          <motion.div className="pin-menu surface" role="menu" aria-label={t('Show on the map')}
            initial={{ opacity: 0, y: 16, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.95 }} transition={spring}>
            <div className="pm-title">{t('Show on the map')}</div>
            {OPTIONS.map((o) => {
              const on = values[o.param] !== false
              return (
                <button key={o.id} role="menuitemcheckbox" aria-checked={on} className={`pm-opt ${on ? 'on' : ''}`} onClick={() => set(o.param, !on)}>
                  <span className="pm-emoji" aria-hidden="true">{o.emoji}</span>
                  <span className="pm-label">{t(o.label)}</span>
                  <span className={`ctl-toggle ${on ? 'on' : ''}`} aria-hidden="true"><span className="ctl-knob" /></span>
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
      <button className={`tb pin-btn ${open ? 'open' : ''}`} onClick={() => setOpen(!open)} title={t('Show on the map')} aria-haspopup="menu" aria-expanded={open}>
        <Pin size={20} />
        <small>{t('Pins')}</small>
      </button>
    </div>
  )
}
