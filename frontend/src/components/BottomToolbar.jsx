import { useLayoutEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { useLang } from '../i18n'
import { LangSwitch } from './LangSwitch'
import { Home, Minus, Moon, Plus, Sun } from './Icons'
import { PinMenu } from './PinMenu'

const WINDOWS = [['today', 'Today'], ['weekend', 'Weekend'], ['week', 'Week'], ['month', 'Month']]

/**
 * Centred: [pins] | [-] [home] [+] | [dark] [Today·Weekend·Week·Month] | [language]. Busy areas live in the pins box.
 * Always one row. When the space is narrower than the bar (a small phone, or the slide-over open), the whole bar
 * scales down to fit: --fit = available width / natural width, times the editor's "Toolbar scale".
 */
const EDGE = 12 // px kept free on each side
export function BottomToolbar({ onZoom, onHome }) {
  const { values, set } = useConfig()
  const spring = useSpring()
  const { t } = useLang()
  const dark = values.darkMode
  const idx = Math.max(0, WINDOWS.findIndex(([v]) => v === values.timeWindow))
  const bar = useRef(null)
  useLayoutEffect(() => {
    const el = bar.current
    if (!el) return
    const fit = () => {
      const room = (el.parentElement?.clientWidth || window.innerWidth) - 2 * EDGE
      const userScale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--toolbarScale')) || 1
      el.style.setProperty('--fit', String(Math.min(1, room / (el.offsetWidth * userScale)))) // offsetWidth ignores `scale`
    }
    fit()
    const ro = new ResizeObserver(fit) // the bar's own width changes with the language; the wrap's with the window / slide-over
    ro.observe(el)
    if (el.parentElement) ro.observe(el.parentElement)
    return () => ro.disconnect()
  }, [values.toolbarScale])
  return (
    <motion.div className="toolbar-wrap" initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ ...spring, delay: 0.2 }}>
      <div className="toolbar surface" ref={bar}>
        <PinMenu />
        <span className="sep" />
        <button className="tb" onClick={() => onZoom(-1)} title={t('Zoom out')}><Minus size={20} /><small>{t('Out')}</small></button>
        <button className="tb home" onClick={onHome} title={t('Whole city')}><Home size={22} /><small>{t('City')}</small></button>
        <button className="tb" onClick={() => onZoom(1)} title={t('Zoom in')}><Plus size={20} /><small>{t('In')}</small></button>
        <span className="sep" />
        <button className={`tb ${dark ? 'on' : ''}`} onClick={() => set('darkMode', !dark)} title={t('Dark mode')}>
          <motion.span key={dark ? 'm' : 's'} initial={{ rotate: -90, scale: 0.5, opacity: 0 }} animate={{ rotate: 0, scale: 1, opacity: 1 }} transition={spring} style={{ display: 'flex' }}>
            {dark ? <Sun size={20} /> : <Moon size={20} />}
          </motion.span>
          <small>{t(dark ? 'Light' : 'Dark')}</small>
        </button>
        <div className="seg" role="radiogroup" aria-label={t('Time window')}>
          <motion.span className="seg-thumb" animate={{ x: `${idx * 100}%` }} transition={spring} />
          {WINDOWS.map(([v, label]) => (
            <button key={v} role="radio" aria-checked={values.timeWindow === v} className={`seg-opt ${values.timeWindow === v ? 'on' : ''}`} onClick={() => set('timeWindow', v)}>{t(label)}</button>
          ))}
        </div>
        <span className="sep" />
        <LangSwitch />
      </div>
    </motion.div>
  )
}
