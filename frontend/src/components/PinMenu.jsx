import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { PIN_GROUPS } from '../data/pinGroups'
import { useLang } from '../i18n'
import { Pin } from './Icons'

/**
 * First toolbar button: tap -> a box slides up (like the language picker) with a toggle per kind of pin.
 * Tap a row to switch that kind on or off; tap outside the box or the pin button again to close it.
 * The badge on the button says how many kinds are on when some are switched off.
 */
export function PinMenu({ counts }) {
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

  const onCount = PIN_GROUPS.filter((g) => values[g.param] !== false).length
  return (
    <div className="pinmenu" ref={ref}>
      <AnimatePresence>
        {open && (
          <motion.div className="pin-menu surface" role="menu" aria-label={t('Show on the map')}
            initial={{ opacity: 0, y: 16, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.95 }} transition={spring}>
            <div className="pm-title">{t('Show on the map')}</div>
            {PIN_GROUPS.map((g) => {
              const on = values[g.param] !== false
              return (
                <button key={g.id} role="menuitemcheckbox" aria-checked={on} className={`pm-opt ${on ? 'on' : ''}`} onClick={() => set(g.param, !on)}>
                  <span className="pm-emoji" aria-hidden="true">{g.emoji}</span>
                  <span className="pm-label">{t(g.label)}</span>
                  <span className="pm-count">{counts?.[g.id] ?? ''}</span>
                  <span className={`ctl-toggle ${on ? 'on' : ''}`} aria-hidden="true"><span className="ctl-knob" /></span>
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
      <button className={`tb pin-btn ${open ? 'open' : ''}`} onClick={() => setOpen(!open)} title={t('Show on the map')} aria-haspopup="menu" aria-expanded={open}>
        <Pin size={20} />
        {onCount < PIN_GROUPS.length && <span className="pm-badge">{onCount}</span>}
        <small>{t('Pins')}</small>
      </button>
    </div>
  )
}
