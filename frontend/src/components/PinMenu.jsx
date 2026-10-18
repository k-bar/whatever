import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { PIN_GROUPS } from '../data/pinGroups'
import { CITY_LAYERS } from './cityLayers'
import { useLang } from '../i18n'
import { Pin } from './Icons'
import { handToPinMenu } from '../data/mapFilter'
import { usePopover } from '../hooks/usePopover'

// one list: the busy-areas heatmap first (it used to be its own toolbar button), the kinds of pins, then the
// city's own layers (toilets / AED near your route, walking routes), and "Open now" (places whose opening
// hours say they're open right now; off by default)
const BUSY = { id: 'busy', param: 'busyAreas', label: 'Busy areas', emoji: '🔥' }
const OPEN_NOW = { id: 'open', param: 'openNow', label: 'Open now', emoji: '🕒' }
const OPTIONS = [BUSY, ...PIN_GROUPS, ...CITY_LAYERS, OPEN_NOW]
// the pin kinds: touching one hands the map back from the event search to this menu (last one used wins)
const PIN_OPTION_IDS = new Set([...PIN_GROUPS.map((g) => g.id), OPEN_NOW.id])

/**
 * First toolbar button: tap -> a compact box slides up (like the language picker) with a toggle per kind
 * of thing on the map. Only Events is on by default; tap a row to switch the others on. Tap outside the box or
 * the pin button again to close it. How many of each there are lives in Settings -> Data sources.
 */
export function PinMenu() {
  const { values, set } = useConfig()
  const { t } = useLang()
  const spring = useSpring()
  const { open, setOpen, ref } = usePopover() // closes on a tap outside and on Escape

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
                <button key={o.id} data-opt={o.id} role="menuitemcheckbox" aria-checked={on} className={`pm-opt ${on ? 'on' : ''}`} onClick={() => { set(o.param, !on); if (PIN_OPTION_IDS.has(o.id)) handToPinMenu() }}>
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
