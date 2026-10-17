import { motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { Flame, Home, Layers, Minus, Moon, Plus, Sun } from './Icons'

const WINDOWS = [['today', 'Today'], ['weekend', 'Weekend'], ['week', 'Week'], ['month', 'Month']]

/** Centred, symmetrical: [venues] [busy areas] | [-] [home] [+] | [dark] [Today·Weekend·Week·Month] */
export function BottomToolbar({ busy, onBusy, onZoom, onHome, onLayers, layersOn }) {
  const { values, set } = useConfig()
  const spring = useSpring()
  const dark = values.darkMode
  const idx = Math.max(0, WINDOWS.findIndex(([v]) => v === values.timeWindow))
  return (
    <motion.div className="toolbar-wrap" initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ ...spring, delay: 0.2 }}>
      <div className="toolbar surface">
        <button className={`tb ${layersOn ? 'on' : ''}`} onClick={onLayers} title="Venues layer"><Layers size={20} /><small>Venues</small></button>
        <button className={`tb busy ${busy ? 'on' : ''}`} onClick={onBusy} title="Busy areas"><Flame size={20} /><small>Busy</small></button>
        <span className="sep" />
        <button className="tb" onClick={() => onZoom(-1)} title="Zoom out"><Minus size={20} /><small>Out</small></button>
        <button className="tb home" onClick={onHome} title="Whole city"><Home size={22} /><small>City</small></button>
        <button className="tb" onClick={() => onZoom(1)} title="Zoom in"><Plus size={20} /><small>In</small></button>
        <span className="sep" />
        <button className={`tb ${dark ? 'on' : ''}`} onClick={() => set('darkMode', !dark)} title="Dark mode">
          <motion.span key={dark ? 'm' : 's'} initial={{ rotate: -90, scale: 0.5, opacity: 0 }} animate={{ rotate: 0, scale: 1, opacity: 1 }} transition={spring} style={{ display: 'flex' }}>
            {dark ? <Sun size={20} /> : <Moon size={20} />}
          </motion.span>
          <small>{dark ? 'Light' : 'Dark'}</small>
        </button>
        <div className="seg" role="radiogroup" aria-label="Time window">
          <motion.span className="seg-thumb" animate={{ x: `${idx * 100}%` }} transition={spring} />
          {WINDOWS.map(([v, label]) => (
            <button key={v} role="radio" aria-checked={values.timeWindow === v} className={`seg-opt ${values.timeWindow === v ? 'on' : ''}`} onClick={() => set('timeWindow', v)}>{label}</button>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
