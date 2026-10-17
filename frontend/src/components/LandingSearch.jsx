import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { categoryColor } from '../data/categories'
import { locale, useLang } from '../i18n'
import { geocodeWarsaw, whenPresets, whereSuggestions } from '../landing/search'
import { Calendar, fmtDay, usePopover } from './Calendar'
import { Calendar as CalendarIcon, MapIcon, Pin, Search, Sparkle, X } from './Icons'

const WHERE_ICON = { type: Sparkle, district: MapIcon, venue: Pin, place: Pin }

export function whenLabel(w) {
  if (!w) return null
  if (w.preset) return w.label
  const same = w.from.toDateString() === w.to.toDateString()
  return same ? fmtDay(w.from) : `${w.from.toLocaleDateString(locale(), { day: 'numeric', month: 'short' })} – ${w.to.toLocaleDateString(locale(), { day: 'numeric', month: 'short' })}`
}

/** "When": quick picks + a range calendar. Optional. onDone: a quick pick or Done was pressed. */
export function WhenPart({ value, onChange, onDone }) {
  const { t } = useLang()
  const spring = useSpring()
  const { open, setOpen, ref } = usePopover()
  const presets = useMemo(whenPresets, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const range = value ? { from: value.from, to: value.to } : undefined
  return (
    <div className="hs-part hs-when" ref={ref}>
      <button type="button" className={`hs-field ${value ? 'set' : ''}`} onClick={() => setOpen(!open)} aria-expanded={open}>
        <CalendarIcon size={17} />
        <span className="hs-text"><small>{t('When')}</small>{whenLabel(value) || t('Any time')}</span>
      </button>
      {value && <button type="button" className="hs-clear" onClick={() => onChange(null)} aria-label={t('Clear')}><X size={14} stroke={2.4} /></button>}
      <AnimatePresence>
        {open && (
          <motion.div className="hs-pop cal-pop surface" initial={{ opacity: 0, y: -8, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.97 }} transition={spring}>
            <div className="when-presets">
              {presets.map((p) => (
                <button type="button" key={p.label} className={`when-chip ${value?.label === p.label ? 'on' : ''}`} onClick={() => { onChange({ ...p, preset: true }); setOpen(false); onDone?.() }}>{p.label}</button>
              ))}
            </div>
            <Calendar mode="range" selected={range} defaultMonth={value?.from}
              onSelect={(r) => { if (r?.from) onChange({ from: r.from, to: r.to || r.from }) }} />
            <div className="when-foot">
              <button type="button" className="btn text small" onClick={() => onChange(null)}>{t('Any time')}</button>
              <button type="button" className="btn small primary" onClick={() => { setOpen(false); onDone?.() }}>{t('Done')}</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** "Where": type a district, venue, event type or address. Optional. */
export function WherePart({ value, onChange, features }) {
  const { t } = useLang()
  const spring = useSpring()
  const { open, setOpen, ref } = usePopover()
  const [text, setText] = useState(value?.label || '')
  const [places, setPlaces] = useState([])
  const local = useMemo(() => whereSuggestions(text, features), [text, features])

  useEffect(() => {
    setPlaces([])
    if (text.trim().length < 3 || value?.label === text) return
    const ctl = new AbortController()
    const timer = setTimeout(() => geocodeWarsaw(text, ctl.signal).then(setPlaces).catch(() => {}), 400)
    return () => { clearTimeout(timer); ctl.abort() }
  }, [text]) // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (s) => { onChange(s); setText(s.label); setOpen(false) }
  const list = [...local, ...places.filter((p) => !local.some((l) => l.label === p.label))].slice(0, 8)
  const kindLabel = { type: t('Event type'), district: t('District'), venue: t('Venue'), place: t('Address') }

  return (
    <div className="hs-part hs-where" ref={ref}>
      <label className={`hs-field ${value ? 'set' : ''}`}>
        <Pin size={17} />
        <span className="hs-text"><small>{t('Where')}</small>
          <input value={text} placeholder={t('Anywhere')} onFocus={() => setOpen(true)}
            onChange={(e) => { setText(e.target.value); setOpen(true); onChange(e.target.value.trim() ? { kind: 'text', label: e.target.value.trim() } : null) }} />
        </span>
      </label>
      {text && <button type="button" className="hs-clear" onClick={() => { setText(''); onChange(null) }} aria-label={t('Clear')}><X size={14} stroke={2.4} /></button>}
      <AnimatePresence>
        {open && list.length > 0 && (
          <motion.div className="hs-pop where-pop surface" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={spring}>
            {list.map((s) => {
              const I = WHERE_ICON[s.kind]
              return (
                <button type="button" key={`${s.kind}:${s.label}`} className="where-opt" onClick={() => pick(s)}>
                  <span className="ic" style={s.category ? { color: categoryColor(s.category) } : {}}><I size={16} /></span>
                  <span className="t">{s.label}</span><small>{kindLabel[s.kind]}</small>
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/**
 * The start page's search pill: what (½) · when (¼) · where (¼). When and where are optional; the
 * search button always works. onSearch({ q, when, where }).
 */
export function LandingSearch({ features, onSearch }) {
  const { t } = useLang()
  const [q, setQ] = useState('')
  const [when, setWhen] = useState(null)
  const [where, setWhere] = useState(null)
  const submit = (e) => { e?.preventDefault(); onSearch({ q: q.trim(), when, where, summary: [q.trim(), whenLabel(when), where?.label].filter(Boolean).join(' · ') }) }
  return (
    <motion.form className="hero-search hs surface" onSubmit={submit}>
      <label className="hs-part hs-what">
        <Search size={19} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("What's the plan today?")} aria-label={t('Search')} autoFocus />
      </label>
      <span className="hs-sep" />
      <WhenPart value={when} onChange={setWhen} />
      <span className="hs-sep" />
      <WherePart value={where} onChange={setWhere} features={features} />
      <button type="submit" className="hero-go" aria-label={t('Search')}><Search size={22} /></button>
    </motion.form>
  )
}
