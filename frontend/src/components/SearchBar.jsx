import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { Burger, Calendar, Chevron, Database, History, Message, Plus, Search, Sparkle, Star, User, X, Minus } from './Icons'
import { CATEGORIES, categoryColor, categoryLabel } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { CloseButton } from './CloseButton'

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

const SUGGESTED = ['jazz tonight', 'run club', 'Praga nightlife', 'free exhibitions', 'picnic', 'stand-up', 'teatr', 'Mokotów']
const RECENT_KEY = 'warszawa-live.recent.v1'
const readRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] } }

/**
 * The Gemini-style pill: burger (plain) · input · mode dropdown · spyglass (circle).
 * Focusing the input opens the focus panel (recents / category pills / assistant thread).
 */
export function SearchBar({ onSearch, onMenu, results, onPick, onClear, searching, mobile, chat, onChatClear }) {
  const { values } = useConfig()
  const spring = useSpring()
  const bouncy = useSpring({ stiffness: 520, damping: 18 })
  const [q, setQ] = useState('')
  const [mode, setMode] = useState('search')
  const [modeOpen, setModeOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const [chatFull, setChatFull] = useState(false)
  const [recent, setRecent] = useState(readRecent)
  const [pushed, setPushed] = useState(false)
  const wrapRef = useRef(null)
  const inputRef = useRef(null)
  const Mode = MODES.find((m) => m.id === mode)

  useEffect(() => {
    const onDoc = (e) => { if (!wrapRef.current?.contains(e.target)) { setModeOpen(false); setMenuOpen(false); setFocused(false) } }
    document.addEventListener('pointerdown', onDoc)
    return () => document.removeEventListener('pointerdown', onDoc)
  }, [])

  const remember = (term) => {
    if (!term.trim()) return
    const next = [term.trim(), ...recent.filter((r) => r !== term.trim())].slice(0, 8)
    setRecent(next); localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  }

  const submit = (term = q, m = mode, opts) => {
    setPushed(true)
    setTimeout(() => setPushed(false), 260 / (values.animSpeed || 1))
    setModeOpen(false); setMenuOpen(false)
    remember(term)
    if (m !== 'assistant') { setFocused(false); inputRef.current?.blur() } else setQ('')
    onSearch(m, term, opts)
  }
  const clear = () => { setQ(''); onClear(); setFocused(false) }
  const pickCategory = (slug) => { const label = categoryLabel(slug); setQ(label); submit(label, 'events', { category: slug }) }

  const panelOpen = values.searchPanel && focused && !menuOpen && !modeOpen && (mode === 'assistant' || !results || q !== (results?.q || ''))
  const showResults = results && !menuOpen && !mobile && !panelOpen && mode !== 'assistant'
  const showAssistant = mode === 'assistant' && (focused || chatFull) && !menuOpen && !modeOpen && values.searchPanel

  return (
    <div className="search-wrap" ref={wrapRef}>
      <span className="search-glow" />
      <motion.div className="search surface" animate={pushed ? { y: 10, scale: 0.985 } : { y: 0, scale: 1 }} transition={spring}>
        <motion.button className="btn icon burger-btn" aria-label="Menu" onClick={() => { setMenuOpen(!menuOpen); setModeOpen(false); setFocused(false) }}
          animate={{ rotate: menuOpen ? 90 : 0 }} transition={bouncy}>
          {menuOpen ? <X size={26} stroke={2.2} /> : <Burger />}
        </motion.button>
        <input ref={inputRef} value={q} placeholder={mode === 'assistant' ? 'Ask the assistant…' : values.searchPlaceholder} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') { setFocused(false); inputRef.current?.blur() } }}
          onFocus={() => { setMenuOpen(false); setModeOpen(false); setFocused(true) }} />
        {(q || results) && <button className="btn icon small ghost" onClick={clear} aria-label="Clear"><X size={20} stroke={2.2} /></button>}
        <button className={`mode-btn ${modeOpen ? 'open' : ''}`} onClick={() => { setModeOpen(!modeOpen); setMenuOpen(false) }}>
          {!mobile && <Mode.Icon size={15} />}{!mobile && Mode.label}
          {mobile && <Mode.Icon size={16} />}
          <Chevron size={14} className="chev" />
        </button>
        <motion.button className={`btn icon go ${mode === 'assistant' ? 'accent' : ''}`} onClick={() => submit()} aria-label="Run search"
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
              <button key={m.id} className={m.id === mode ? 'on' : ''} onClick={() => { setMode(m.id); setModeOpen(false); setFocused(true); inputRef.current?.focus() }}>
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

      {/* focus panel: recents (search) · category pills (events) · thread (assistant) */}
      <AnimatePresence>
        {(panelOpen || showAssistant) && (
          <motion.div key={mode} className={`focus-panel surface mode-${mode} ${chatFull && mode === 'assistant' ? 'full' : ''}`}
            initial={{ opacity: 0, y: -14, scaleY: 0.92 }} animate={{ opacity: 1, y: 0, scaleY: 1 }} exit={{ opacity: 0, y: -10, scaleY: 0.95 }} transition={spring} style={{ transformOrigin: 'top' }}
            onPointerDown={(e) => e.stopPropagation()}>
            {mode === 'search' && (
              <div className="fp-scroll">
                {recent.length > 0 && <>
                  <div className="blk-title fp-title"><History size={12} /> Recent</div>
                  <div className="fp-list">{recent.map((r) => <button key={r} className="fp-item" onClick={() => { setQ(r); submit(r, 'search') }}><History size={15} />{r}</button>)}</div>
                </>}
                <div className="blk-title fp-title"><Sparkle size={12} /> Suggested</div>
                <div className="fp-list">{SUGGESTED.map((r) => <button key={r} className="fp-item" onClick={() => { setQ(r); submit(r, 'search') }}><Search size={15} />{r}</button>)}</div>
              </div>
            )}
            {mode === 'events' && (
              <div className="fp-scroll">
                <div className="blk-title fp-title"><Calendar size={12} /> Pick a category</div>
                <div className="pills">
                  {Object.entries(CATEGORIES).map(([slug, c]) => (
                    <button key={slug} className="pill-cat" style={{ '--c': c.color }} onClick={() => pickCategory(slug)}><i />{c.label}</button>
                  ))}
                </div>
              </div>
            )}
            {mode === 'assistant' && (
              <>
                <div className="fp-scroll chat">
                  {!chat?.length && <div className="chat-empty"><Sparkle size={22} /><p>One continuous thread. Ask things like “what's on in Praga tonight?” or “free things with kids on Saturday”.</p></div>}
                  {chat?.map((m, i) => (
                    <div key={i} className={`msg ${m.role}`}>
                      <div className="bubble">{m.text}</div>
                      {m.results?.length > 0 && <div className="msg-results">{m.results.slice(0, 4).map((f) => (
                        <button key={f.id} className="res-item mini" onClick={() => onPick(f)}>
                          <span className="thumb" style={f.properties.image_url ? { backgroundImage: `url(${f.properties.image_url})` } : { background: categoryColor(f.properties.categories?.[0]) }}>{!f.properties.image_url && f.properties.title[0]}</span>
                          <span><div className="t">{f.properties.title}</div><div className="s">{f.properties.kind === 'event' ? fmtWhen(f.properties.starts_at) : f.properties.venue_name}</div></span>
                        </button>))}</div>}
                    </div>
                  ))}
                  {searching && <div className="msg assistant"><div className="bubble typing"><i /><i /><i /></div></div>}
                </div>
                <div className="fp-foot">
                  <button className="btn icon small primary" onClick={() => setChatFull(!chatFull)} aria-label={chatFull ? 'Shrink' : 'Expand'}>{chatFull ? <Minus size={18} /> : <Plus size={18} />}</button>
                  <span className="fp-hint">{chat?.length ? `${chat.length} messages` : 'assistant · stub'}</span>
                  {chat?.length > 0 && <button className="btn text small" onClick={onChatClear}>Clear thread</button>}
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* desktop results slide down from under the bar; mobile uses the bottom sheet */}
      <AnimatePresence>
        {showResults && (
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
        {onClear && <CloseButton size={34} onClick={onClear} label="Close results" />}
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
