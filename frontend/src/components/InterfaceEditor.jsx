import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { SECTIONS } from '../config/schema'
import { useConfig, useSpring } from '../config/store'
import { Check, Chevron, ChevronL, ChevronR, Sliders, X } from './Icons'
import { useIsMobile } from '../hooks/useMedia'

/* ---------- controls ---------- */

function SelectControl({ param, value, onChange }) {
  const idx = param.options.findIndex((o) => o.value === value)
  const step = (d) => onChange(param.options[(idx + d + param.options.length) % param.options.length].value)
  return (
    <div className="ctl-select">
      <button className="ctl-arrow" onClick={() => step(-1)} aria-label="previous"><ChevronL size={16} /></button>
      <div className="ctl-dd">
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          {param.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <Chevron size={14} className="ctl-dd-chev" />
      </div>
      <button className="ctl-arrow" onClick={() => step(1)} aria-label="next"><ChevronR size={16} /></button>
    </div>
  )
}

function RangeControl({ param, value, onChange }) {
  const num = Number(value)
  const display = param.step < 1 ? num.toFixed(2).replace(/\.?0+$/, '') : num
  return (
    <div className="ctl-range">
      <input type="range" min={param.min} max={param.max} step={param.step} value={num}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ '--pct': `${((num - param.min) / (param.max - param.min)) * 100}%` }} />
      <span className="ctl-val">{display}{param.unit || ''}</span>
    </div>
  )
}

function ToggleControl({ value, onChange }) {
  return (
    <button className={`ctl-toggle ${value ? 'on' : ''}`} onClick={() => onChange(!value)} role="switch" aria-checked={value}>
      <motion.span className="ctl-knob" layout transition={{ type: 'spring', stiffness: 600, damping: 32 }} />
    </button>
  )
}

function ColorControl({ param, value, onChange }) {
  return (
    <div className="ctl-colors">
      {param.options.map((c) => (
        <button key={c} className={`ctl-swatch ${c === value ? 'on' : ''}`} style={{ background: c }} onClick={() => onChange(c)} aria-label={c}>
          {c === value && <Check size={14} stroke={3} />}
        </button>
      ))}
      <label className="ctl-swatch custom" title="Custom">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} />
      </label>
    </div>
  )
}

function TextControl({ value, onChange }) {
  return <input className="ctl-text" value={value} onChange={(e) => onChange(e.target.value)} />
}

const CONTROLS = { select: SelectControl, range: RangeControl, toggle: ToggleControl, color: ColorControl, text: TextControl }

/* ---------- tray ---------- */

function Section({ section, values, set }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="ed-section">
      <button className="ed-section-h" onClick={() => setOpen(!open)}>
        <span>{section.label}</span>
        <motion.span animate={{ rotate: open ? 0 : -90 }}><Chevron size={16} /></motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }} style={{ overflow: 'hidden' }}>
            {section.params.map((param) => {
              const Ctl = CONTROLS[param.type]
              const inline = param.type === 'toggle'
              return (
                <div key={param.id} className={`ed-row ${inline ? 'inline' : ''}`}>
                  <label className="ed-label">{param.label}</label>
                  <Ctl param={param} value={values[param.id]} onChange={(v) => set(param.id, v)} />
                </div>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function InterfaceEditor({ open, onToggle }) {
  const { values, set, save, reset, revert, dirty, status } = useConfig()
  const spring = useSpring()
  const mobile = useIsMobile()
  const [q, setQ] = useState('')
  const sections = q
    ? SECTIONS.map((s) => ({ ...s, params: s.params.filter((p) => p.label.toLowerCase().includes(q.toLowerCase())) })).filter((s) => s.params.length)
    : SECTIONS

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button key="fab" className="btn icon ed-fab" onClick={onToggle} aria-label="Open interface editor"
            initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }} transition={spring}>
            <Sliders />
            {dirty && <span className="dot" />}
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.aside key="tray" className="ed-tray surface" initial={{ x: mobile ? '100%' : 420, opacity: 0.6 }}
            animate={{ x: 0, opacity: 1 }} exit={{ x: mobile ? '100%' : 420, opacity: 0.6 }} transition={spring}>
            <header className="ed-head">
              <div className="ed-title">
                <Sliders size={18} />
                <h2>Interface editor</h2>
              </div>
              <div className="ed-actions">
                <button className={`btn pill small ${dirty ? 'primary' : ''}`} onClick={save} disabled={!dirty && status === 'idle'}>
                  {status === 'saving' ? 'Saving…' : status === 'saved' ? 'Saved ✓' : status === 'local' ? 'Saved locally' : dirty ? 'Save' : 'Saved'}
                </button>
                <button className="btn icon small ghost" onClick={onToggle} aria-label="Close editor"><X size={18} /></button>
              </div>
            </header>
            <div className="ed-tools">
              <input className="ctl-text" placeholder="Filter settings…" value={q} onChange={(e) => setQ(e.target.value)} />
              <button className="btn text small" onClick={revert} disabled={!dirty}>Revert</button>
              <button className="btn text small" onClick={reset}>Defaults</button>
            </div>
            <div className="ed-scroll">
              {sections.map((s) => <Section key={s.id} section={s} values={values} set={set} />)}
              <p className="ed-foot">Every control here changes something live. Add new ones in <code>src/config/schema.js</code>.</p>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
