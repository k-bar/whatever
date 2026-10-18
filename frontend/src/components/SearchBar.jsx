import { Fragment, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { Burger, Calendar, Chevron, History, Plus, Search, Sparkle, X, Minus } from './Icons'
import { CATEGORIES, categoryColor, categoryLabel } from '../data/categories'
import { fmtWhenFor } from '../mapboxes/curate'
import { CloseButton } from './CloseButton'
import { useLang } from '../i18n'
import { WhenPart, WherePart, whenLabel } from './LandingSearch'
import { FLIGHT_MS } from '../landing/searchFlight'

export const MODES = [
  { id: 'search', label: 'Search', hint: 'Places, venues, districts', Icon: Search },
  { id: 'events', label: 'Events', hint: 'Only things with a date', Icon: Calendar },
  { id: 'assistant', label: 'Assistant', hint: 'Ask in plain words', Icon: Sparkle },
]

/** The burger's spin-and-switch and the tray: the same calm "push" as the search pill's flight (landing/searchFlight.js). */
export function usePush() {
  const { values } = useConfig()
  return values.reduceMotion ? { duration: 0.1 } : { duration: FLIGHT_MS / 1000 / (values.animSpeed || 1), ease: [0.4, 0, 0.2, 1] }
}

const SUGGESTED = ['jazz tonight', 'run club', 'Praga nightlife', 'free exhibitions', 'picnic', 'stand-up', 'teatr', 'Mokotów']
const RECENT_KEY = 'warszawa-live.recent.v1'
const readRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] } }

/**
 * The Gemini-style pill: burger (plain) · input · mode dropdown · spyglass (circle).
 * Focusing the input opens the focus panel (recents / category pills / assistant thread).
 */
export function SearchBar({ onSearch, trayOpen = false, unread = 0, onBurger, results, onPick, onClear, searching, mobile, chat, onChatClear, initialQuery = '', features }) {
  const { values } = useConfig()
  const { t } = useLang()
  const spring = useSpring()
  const bouncy = useSpring({ stiffness: 520, damping: 18 })
  const push = usePush()
  const [q, setQ] = useState(initialQuery)
  const placeholder = values.searchPlaceholder === 'Search Warsaw tonight…' ? "What's the plan today?" : values.searchPlaceholder
  const [mode, setMode] = useState('search')
  const [modeOpen, setModeOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const [chatFull, setChatFull] = useState(false)
  const [recent, setRecent] = useState(readRecent)
  const [pushed, setPushed] = useState(false)
  const wrapRef = useRef(null)
  const inputRef = useRef(null)
  const Mode = MODES.find((m) => m.id === mode)
  // Events: what (a tag) · when · where. Runs by itself once all three are chosen, or on the search button.
  const [evCat, setEvCat] = useState(null)
  const [evWhen, setEvWhen] = useState(null)
  const [evWhenDone, setEvWhenDone] = useState(false) // a quick pick or Done, not just the first click of a range
  const [evWhere, setEvWhere] = useState(null)

  useEffect(() => {
    const onDoc = (e) => { if (!wrapRef.current?.contains(e.target)) { setModeOpen(false); setFocused(false) } }
    document.addEventListener('pointerdown', onDoc)
    return () => document.removeEventListener('pointerdown', onDoc)
  }, [])

  const remember = (term) => {
    if (!term.trim()) return
    const next = [term.trim(), ...recent.filter((r) => r !== term.trim())].slice(0, 8)
    setRecent(next); localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  }

  const submit = (term = q, m = mode, opts) => {
    if (m === 'events' && !opts) { // search button / Enter in Events: use the tag, when and where picked so far
      opts = { category: evCat, when: evWhen, where: evWhere }
      term = [evCat ? categoryLabel(evCat) : term.trim(), whenLabel(evWhen), evWhere?.label].filter(Boolean).join(' · ')
    }
    setPushed(true)
    setTimeout(() => setPushed(false), 260 / (values.animSpeed || 1))
    setModeOpen(false)
    remember(term)
    if (m !== 'assistant') { setFocused(false); inputRef.current?.blur() } else setQ('')
    onSearch(m, term, opts)
  }
  const clear = () => { setQ(''); onClear(); setFocused(false) }
  const pickCategory = (slug) => { const off = evCat === slug; setEvCat(off ? null : slug); setQ(off ? '' : categoryLabel(slug)) }
  const evReady = !!(evCat && evWhen && evWhenDone && evWhere && evWhere.kind !== 'text') // typed-but-not-picked "where" waits
  // all three chosen → search; changing any of them afterwards searches again
  useEffect(() => { if (evReady) submit() }, [evReady, evCat, evWhen, evWhenDone, evWhere]) // eslint-disable-line react-hooks/exhaustive-deps

  const panelOpen = values.searchPanel && focused && !modeOpen && (mode === 'assistant' || !results || q !== (results?.q || ''))
  const showResults = results && !mobile && !panelOpen && mode !== 'assistant'
  const showAssistant = mode === 'assistant' && (focused || chatFull) && !modeOpen && values.searchPanel

  return (
    <div className="search-wrap" ref={wrapRef}>
      <span className="search-glow" />
      {/* arriving from / leaving for the start page is a separate flight (landing/searchFlight.js) */}
      <motion.div className="search surface" animate={pushed ? { y: 10, scale: 0.985 } : { y: 0, scale: 1 }} transition={spring}>
        {/* opens / closes the slide-over tray; the burger spins out as the (x) spins in, and back */}
        <button className="btn icon burger-btn" aria-label={t(trayOpen ? 'Close menu' : 'Menu')} aria-expanded={trayOpen}
          onClick={() => { onBurger?.(); setModeOpen(false); setFocused(false) }}>
          <AnimatePresence initial={false}>
            <motion.span key={trayOpen ? 'x' : 'burger'} className="burger-ic"
              initial={{ rotate: -90, opacity: 0, scale: 0.6 }} animate={{ rotate: 0, opacity: 1, scale: 1 }} exit={{ rotate: 90, opacity: 0, scale: 0.6 }} transition={push}>
              {trayOpen ? <X size={26} stroke={2.2} /> : <Burger />}
            </motion.span>
          </AnimatePresence>
          {unread > 0 && !trayOpen && <span className="burger-dot" aria-label={t('{n} unread', { n: unread })} />}
        </button>
        <input ref={inputRef} value={q} placeholder={mode === 'assistant' ? t('Ask the assistant…') : t(placeholder)} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') { setFocused(false); inputRef.current?.blur() } }}
          onFocus={() => { setModeOpen(false); setFocused(true) }} />
        {(q || results) && <button className="btn icon small ghost" onClick={clear} aria-label={t('Clear')}><X size={20} stroke={2.2} /></button>}
        <button className={`mode-btn ${modeOpen ? 'open' : ''}`} onClick={() => setModeOpen(!modeOpen)}>
          {t(Mode.label)}
          <Chevron size={14} className="chev" />
        </button>
        <motion.button className={`btn icon go ${mode === 'assistant' ? 'accent' : ''}`} onClick={() => submit()} aria-label={t('Run search')}
          whileTap={{ scale: 0.85 }} animate={searching ? { rotate: 360 } : { rotate: 0 }} transition={searching ? { repeat: Infinity, duration: 0.9, ease: 'linear' } : spring}>
          <Mode.Icon />{/* the chosen mode's icon lives here, on the confirm button; the switch shows only its name */}
        </motion.button>
      </motion.div>

      {/* mode dropdown: Search / Events / Assistant */}
      <AnimatePresence>
        {modeOpen && (
          <motion.div className="mode-menu surface" initial={{ opacity: 0, scale: 0.85, y: -6 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: -6 }} transition={bouncy}>
            {MODES.map((m) => (
              <button key={m.id} className={m.id === mode ? 'on' : ''} onClick={() => { setMode(m.id); setModeOpen(false); setFocused(true); inputRef.current?.focus() }}>
                <m.Icon size={18} /><span>{t(m.label)}<small>{t(m.hint)}</small></span>
              </button>
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
                  <div className="blk-title fp-title"><History size={12} /> {t('Recent')}</div>
                  <div className="fp-list">{recent.map((r) => <button key={r} className="fp-item" onClick={() => { setQ(r); submit(r, 'search') }}><History size={15} />{r}</button>)}</div>
                </>}
                <div className="blk-title fp-title"><Sparkle size={12} /> {t('Suggested')}</div>
                <div className="fp-list">{SUGGESTED.map((r) => <button key={r} className="fp-item" onClick={() => { setQ(r); submit(r, 'search') }}><Search size={15} />{r}</button>)}</div>
              </div>
            )}
            {mode === 'events' && (<>
              <div className="fp-scroll">
                <div className="blk-title fp-title"><Calendar size={12} /> {t('Pick a category')}</div>
                <div className="pills">
                  {Object.entries(CATEGORIES).map(([slug, c]) => (
                    <button key={slug} className={`pill-cat ${evCat === slug ? 'on' : ''}`} style={{ '--c': c.color }} onClick={() => pickCategory(slug)}><i />{categoryLabel(slug)}</button>
                  ))}
                </div>
              </div>
              <div className="ev-pill hs">
                <WhenPart value={evWhen} onChange={(w) => { setEvWhen(w); setEvWhenDone(false) }} onDone={() => setEvWhenDone(true)} />
                <span className="hs-sep" />
                <WherePart value={evWhere} onChange={setEvWhere} features={features} />
                <button type="button" className="hero-go" onClick={() => submit()} aria-label={t('Search')}><Calendar size={19} /></button>
              </div>
            </>)}
            {mode === 'assistant' && (
              <>
                <div className="fp-scroll chat">
                  {!chat?.length && <div className="chat-empty"><Sparkle size={22} /><p>{t("One continuous thread. Ask things like “what's on in Praga tonight?” or “free things with kids on Saturday”.")}</p></div>}
                  {chat?.map((m, i) => (
                    <div key={i} className={`msg ${m.role}`}>
                      <div className="bubble">{m.text}</div>
                      {m.results?.length > 0 && <div className="msg-results">{m.results.slice(0, 4).map((f) => (
                        <button key={f.id} className="res-item mini" onClick={() => onPick(f)}>
                          <span className="thumb" style={f.properties.image_url ? { backgroundImage: `url(${f.properties.image_url})` } : { background: categoryColor(f.properties.categories?.[0]) }}>{!f.properties.image_url && f.properties.title[0]}</span>
                          <span><div className="t">{f.properties.title}</div><div className="s">{f.properties.kind === 'event' ? fmtWhenFor(f.properties) : f.properties.venue_name}</div></span>
                        </button>))}</div>}
                    </div>
                  ))}
                  {searching && <div className="msg assistant"><div className="bubble typing"><i /><i /><i /></div></div>}
                </div>
                <div className="fp-foot">
                  <button className="btn icon small primary" onClick={() => setChatFull(!chatFull)} aria-label={t(chatFull ? 'Shrink' : 'Expand')}>{chatFull ? <Minus size={18} /> : <Plus size={18} />}</button>
                  <span className="fp-hint">{chat?.length ? t('{n} messages', { n: chat.length }) : t('assistant')}</span>
                  {chat?.length > 0 && <button className="btn text small" onClick={onChatClear}>{t('Clear thread')}</button>}
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
  const { t } = useLang()
  const list = results.results || []
  return (
    <>
      <div className="results-h">
        <h3>{results.mode === 'assistant' ? t('Assistant') : t(list.length === 1 ? '{n} result' : '{n} results', { n: list.length })}{results.q ? ` · “${results.q}”` : ''}</h3>
        {onClear && <CloseButton size={34} onClick={onClear} label={t('Close results')} />}
      </div>
      <div className="results-scroll">
        {results.answer && <div className="assistant"><b>✦ </b>{results.answer}</div>}
        {results.exact === 0 && list.length > 0 && <div className="res-near first">{t('No exact matches. Closest:')}</div>}
        {list.map((f, i) => {
          const p = f.properties
          const c = categoryColor(p.categories?.[0])
          return (
            <Fragment key={f.id}>
            {i > 0 && i === results.exact && <div className="res-near">{t('Close matches')}</div>}
            <button className="res-item" onClick={() => onPick(f)} aria-label={p.title}>
              <span className="thumb" style={p.image_url ? { backgroundImage: `url(${p.image_url})` } : { background: c }}>
                {!p.image_url && (p.title || '?')[0]}
              </span>
              <span>
                <div className="t">{p.title}</div>
                <div className="s">
                  {p.kind === 'event' ? fmtWhenFor(p) : (p.venue_type || t('venue')).replace('_', ' ')}
                  {p.venue_name && p.kind === 'event' ? ` · ${p.venue_name}` : ''}
                  {' · '}<span style={{ color: c, fontWeight: 600 }}>{categoryLabel(p.categories?.[0])}</span>
                </div>
              </span>
            </button>
            </Fragment>
          )
        })}
        {!list.length && !results.answer && <div className="res-empty">{t('Nothing found. Try “jazz”, “Praga”, “run” or “teatr”.')}</div>}
      </div>
    </>
  )
}
