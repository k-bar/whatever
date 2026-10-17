import { motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { useLang } from '../i18n'
import { LangSwitch } from './LangSwitch'
import { Flame, Home, Minus, Moon, Pin, Plus, Sun } from './Icons'

const WINDOWS = [['today', 'Today'], ['weekend', 'Weekend'], ['week', 'Week'], ['month', 'Month']]

/** Centred, symmetrical: [pins] [busy areas] | [-] [home] [+] | [dark] [Today·Weekend·Week·Month] | [language] */
export function BottomToolbar({ busy, onBusy, onZoom, onHome, pins, onPins }) {
  const { values, set } = useConfig()
  const spring = useSpring()
  const { t } = useLang()
  const dark = values.darkMode
  const idx = Math.max(0, WINDOWS.findIndex(([v]) => v === values.timeWindow))
  return (
    <motion.div className="toolbar-wrap" initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ ...spring, delay: 0.2 }}>
      <div className="toolbar surface">
        <button className={`tb ${pins ? 'on' : ''}`} onClick={onPins} title={t('Show or hide all pins')}><Pin size={20} /><small>{t('Pins')}</small></button>
        <button className={`tb busy ${busy ? 'on' : ''}`} onClick={onBusy} title={t('Busy areas')}><Flame size={20} /><small>{t('Busy')}</small></button>
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
