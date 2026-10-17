import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { useLang } from '../i18n'
import { LANDUSE, getLanduseHidden, landuseActive, setLanduseHidden } from './mapStyle'

const OPEN_KEY = 'warszawa-live.landuse-key-open.v1'

/**
 * Key for the land-use colours. Tapping a row dims / restores that colour on the map.
 * Lives in the footer of the Data sources panel (embedded); collapsed to its header by default, the
 * choice is remembered.
 */
export function LanduseLegend({ getMap, mobile, embedded = false }) {
  const { values } = useConfig()
  const { t } = useLang()
  const spring = useSpring()
  const [open, setOpen] = useState(() => {
    try { const v = localStorage.getItem(OPEN_KEY); return v === null ? false : v === '1' } catch { return false }
  })
  const [hidden, setHidden] = useState(getLanduseHidden)

  if (!values.landuseLegend || !landuseActive(values)) return null

  const toggleOpen = () => {
    setOpen((o) => { try { localStorage.setItem(OPEN_KEY, o ? '0' : '1') } catch { /* private mode */ } return !o })
  }
  const toggleClass = (key) => {
    const next = new Set(hidden)
    next.has(key) ? next.delete(key) : next.add(key)
    setHidden(next)
    setLanduseHidden(getMap(), next)
  }

  return (
    <div className={`landuse-key ${embedded ? 'embedded' : 'surface'}`}>
      <button className="lk-head" onClick={toggleOpen} aria-expanded={open}>
        <span className="lk-dots">{LANDUSE.slice(0, 4).map((c) => <i key={c.key} style={{ background: c.color }} />)}</span>
        {t('Land use')}
        <motion.svg className="lk-chev" width="12" height="12" viewBox="0 0 12 12" animate={{ rotate: open ? 180 : 0 }} transition={spring}>
          <path d="M3 7.5 6 4.5l3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </motion.svg>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul className="lk-list" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={spring}>
            {LANDUSE.map((c) => (
              <li key={c.key}>
                <button className={hidden.has(c.key) ? 'off' : ''} onClick={() => toggleClass(c.key)} aria-pressed={!hidden.has(c.key)} title={t('Tap a colour to hide it')}>
                  <span className="lk-sw" style={{ background: c.color }} />
                  {t(c.label)}
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}
