import { motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { Flame, Home, Layers, Minus, Moon, Plus, Sun } from './Icons'

/** Symmetrical: [heat] [-] [home] [+] [dark]  (+ optional layers toggle for places/events) */
export function BottomToolbar({ heat, onHeat, onZoom, onHome, onLayers, layersOn }) {
  const { values, set } = useConfig()
  const spring = useSpring()
  const dark = values.darkMode
  return (
    <motion.div className="toolbar-wrap" initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ ...spring, delay: 0.2 }}>
      <div className="toolbar surface">
        <button className={`tb ${layersOn ? 'on' : ''}`} onClick={onLayers} title="Venues layer"><Layers size={20} /><small>Venues</small></button>
        <button className={`tb heat ${heat ? 'on' : ''}`} onClick={onHeat} title="Busy now heatmap"><Flame size={20} /><small>Busy</small></button>
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
        <button className="tb" onClick={() => set('timeWindow', NEXT[values.timeWindow])} title="Time window" style={{ fontSize: 11, fontWeight: 700 }}>
          {LABEL[values.timeWindow]}<small>When</small>
        </button>
      </div>
    </motion.div>
  )
}
const NEXT = { now: 'today', today: 'week', week: 'month', month: 'all', all: 'now' }
const LABEL = { now: '3h', today: 'Today', week: 'Week', month: '30d', all: 'All' }
