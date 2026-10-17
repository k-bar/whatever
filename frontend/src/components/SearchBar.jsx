import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { Burger, Calendar, Chevron, Database, Message, Search, Sparkle, Star, User, X } from './Icons'
import { categoryColor, categoryLabel } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'

export const MODES = [
  { id: 'search', label: 'Search', hint: 'Places, venues, districts', Icon: Search },
  { id: 'events', label: 'Events', hint: 'Only things with a date', Icon: Calendar },
  { id: 'assistant', label: 'Assistant', hint: 'Ask in plain words', Icon: Sparkle },
]

export const MENU_ITEMS = [
  { id: 'profile', label: 'Profiles', Icon: User, hint: 'you' },
  { id: 'messages', label: 'Messages', Icon: Message, hint: '3 new' },
  { id: 'favourites', label: 'Favourite spots', Icon: Star, hint: '' },
  { id: 'sources', label: "APIs I'm plugged in to", Icon: Database, hint: '5 sources' },
]

/**
 * The Gemini-style pill: burger (plain) · input · mode dropdown · spyglass (circle).
 * Props: onSearch(mode, q), onMenu(itemId), results {mode, q, answer, results} | null, onPick(feature), onClear()
 */
export function SearchBar({ onSearch, onMenu, results, onPick, onClear, searching, mobile }) {
  const { values } = useConfig()
  const spring = useSpring()
  const bouncy = useSpring({ stiffness: 520, damping: 18 })
  const [q, setQ] = useState('')
  const [mode, setMode] = useState('search')
  const [modeOpen, setModeOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [pushed, setPushed] = useState(false)
  const wrapRef = useRef(null)
  const Mode = MODES.find((m) => m.id === mode)

  useEffect(() => {
    const onDoc = (e) => { if (!wrapRef.current?.contains(e.target)) { setModeOpen(false); setMenuOpen(false) } }
    document.addEventListener('pointerdown', onDoc)
    return () => document.removeEventListener('pointerdown', onDoc)
  }, [])

  const submit = () => {
    setPushed(true)
    setTimeout(() => setPushed(false), 260 / (values.animSpeed || 1))
    setModeOpen(false); setMenuOpen(false)
    onSearch(mode, q)
  }
  const clear = () => { setQ(''); onClear() }

  return (
    <div className="search-wrap" ref={wrapRef}>
      <span className="search-glow" />
      <motion.div className="search surface" animate={pushed ? { y: 10, scale: 0.985 } : { y: 0, scale: 1 }} transition={spring}>
        <motion.button className="btn icon burger-btn" aria-label="Menu" onClick={() => { setMenuOpen(!menuOpen); setModeOpen(false) }}
          animate={{ rotate: menuOpen ? 90 : 0 }} transition={bouncy}>
          {menuOpen ? <X /> : <Burger />}
        </motion.button>
        <input value={q} placeholder={values.searchPlaceholder} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') clear() }} onFocus={() => setMenuOpen(false)} />
        {(q || results) && <button className="btn icon small ghost" onClick={clear} aria-label="Clear"><X size={16} /></button>}
        <button className={`mode-btn ${modeOpen ? 'open' : ''}`} onClick={() => { setModeOpen(!modeOpen); setMenuOpen(false) }}>
          {!mobile && <Mode.Icon size={15} />}{!mobile && Mode.label}
          {mobile && <Mode.Icon size={16} />}
          <Chevron size={14} className="chev" />
        </button>
        <motion.button className={`btn icon go ${mode === 'assistant' ? 'accent' : ''}`} onClick={submit} aria-label="Run search"
          whileTap={{ scale: 0.85 }} animate={searching ? { rotate: 360 } : { rotate: 0 }} transition={searching ? { repeat: Infinity, duration: 0.9, ease: 'linear' } : spring}>
          {mode === 'assistant' ? <Sparkle /> : <Search />}
        </motion.button>
      </motion.div>

      {/* mode dropdown: Search / Events / Assistant */}
      <AnimatePresence>
        {modeOpen && (
          <motion.div className="mode-menu surface" initial={{ opacity: 0, scale: 0.85, y: -6 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: -6 }} transition={bouncy}>
            {MODES.map((m) => (
              <button key={m.id} className={m.id === mode ? 'on' : ''} onClick={() => { setMode(m.id); setModeOpen(false) }}>
                <m.Icon size={18} /><span>{m.label}<small>{m.hint}</small></span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* burger menu: liquid glass, overshoots then snaps back */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div className="burger-menu surface" initial={{ opacity: 0, scaleX: 0.3, scaleY: 0.1 }}
            animate={{ opacity: 1, scaleX: [0.3, 1.06, 1], scaleY: [0.1, 1.08, 1] }} exit={{ opacity: 0, scaleX: 0.5, scaleY: 0.3 }}
            transition={values.reduceMotion ? { duration: 0.1 } : { duration: 0.42 / (values.animSpeed || 1), times: [0, 0.65, 1], ease: ['easeOut', 'easeInOut'] }}>
            <div className="bm-title">{values.appTitle}</div>
            {MENU_ITEMS.map((it, i) => (
              <motion.button key={it.id} className="bm-item" onClick={() => { setMenuOpen(false); onMenu(it.id) }}
                initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.12 + i * 0.04 }}>
                <span className="ic"><it.Icon size={18} /></span>{it.label}<small>{it.hint}</small>
              </motion.button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* desktop results slide down from under the bar; mobile uses the bottom sheet */}
      <AnimatePresence>
        {results && !menuOpen && !mobile && (
          <motion.div className="results surface desktop" initial={{ opacity: 0, y: -24, scaleY: 0.9 }} animate={{ opacity: 1, y: 0, scaleY: 1 }}
            exit={{ opacity: 0, y: -16 }} transition={spring} style={{ transformOrigin: 'top' }}>
            <ResultsList results={results} onPick={onPick} onClear={clear} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function ResultsList({ results, onPick, onClear }) {
  const list = results.results || []
  return (
    <>
      <div className="results-h">
        <h3>{results.mode === 'assistant' ? 'Assistant' : `${list.length} result${list.length === 1 ? '' : 's'}`}{results.q ? ` · “${results.q}”` : ''}</h3>
        {onClear && <button className="btn icon small ghost" onClick={onClear} aria-label="Close results"><X size={16} /></button>}
      </div>
      <div className="results-scroll">
        {results.answer && <div className="assistant"><b>✦ </b>{results.answer}</div>}
        {list.map((f) => {
          const p = f.properties
          const c = categoryColor(p.categories?.[0])
          return (
            <button key={f.id} className="res-item" onClick={() => onPick(f)}>
              <span className="thumb" style={p.image_url ? { backgroundImage: `url(${p.image_url})` } : { background: c }}>
                {!p.image_url && (p.title || '?')[0]}
              </span>
              <span>
                <div className="t">{p.title}</div>
                <div className="s">
                  {p.kind === 'event' ? fmtWhen(p.starts_at) : (p.venue_type || 'venue').replace('_', ' ')}
                  {p.venue_name && p.kind === 'event' ? ` · ${p.venue_name}` : ''}
                  {' · '}<span style={{ color: c, fontWeight: 600 }}>{categoryLabel(p.categories?.[0])}</span>
                </div>
              </span>
            </button>
          )
        })}
        {!list.length && !results.answer && <div className="res-empty">Nothing found. Try “jazz”, “Praga”, “run” or “teatr”.</div>}
      </div>
    </>
  )
}
