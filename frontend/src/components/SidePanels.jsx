import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchSources } from '../data/api'
import { categoryColor, categoryLabel } from '../data/categories'
import { CloseButton } from './CloseButton'
import { Brand } from './Brand'
import { Burger, Expand, Shrink, Star } from './Icons'
import { MENU_ITEMS } from './SearchBar'
import { StartPointPicker } from './StartPointPicker'
import { locale, useLang } from '../i18n'

const AV = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']

/**
 * The slide-over: a full-height section on the left, "under" the map (straight edges, a divider, no
 * floating corners). The map never moves. Desktop has three modes: map, map + slide-over, slide-over
 * full screen (expand button). Mobile only has full screen. The (x) is the only way to close it; the
 * burger switches what it shows; the syrenka.me lockup goes back to the start page.
 */
export function SlideOver({ section, onSection, onClose, full, onFull, onHome, mobile, children }) {
  const { t } = useLang()
  const [menu, setMenu] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!menu) return
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setMenu(false) }
    document.addEventListener('pointerdown', onDoc)
    return () => document.removeEventListener('pointerdown', onDoc)
  }, [menu])
  return (
    <motion.aside className={`slideover ${full || mobile ? 'full' : ''}`} initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }}
      transition={{ type: 'spring', stiffness: 260, damping: 34 }}>
      <header className="so-bar" ref={ref}>
        <Brand onHome={onHome} />
        <button className={`so-burger ${menu ? 'open' : ''}`} onClick={() => setMenu(!menu)} aria-label={t('Menu')} aria-expanded={menu}><Burger size={22} /></button>
        <div className="so-actions">
          {!mobile && (
            <button className="btn icon so-expand" style={{ width: 34, height: 34, minWidth: 34 }} onClick={onFull} aria-label={t(full ? 'Shrink' : 'Full screen')} title={t(full ? 'Shrink' : 'Full screen')}>
              {full ? <Shrink size={18} stroke={2.2} /> : <Expand size={18} stroke={2.2} />}
            </button>
          )}
          <CloseButton size={34} onClick={onClose} />
        </div>
        <AnimatePresence>
          {menu && (
            <motion.div className="so-menu surface" initial={{ opacity: 0, y: -8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.96 }} transition={{ duration: 0.18 }}>
              {MENU_ITEMS.map((it) => (
                <button key={it.id} className={`bm-item ${it.id === section ? 'on' : ''}`} onClick={() => { setMenu(false); onSection(it.id) }}>
                  <span className="ic"><it.Icon size={18} /></span>{t(it.label)}<small>{it.hint && t(it.hint)}</small>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </header>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={section} className="so-body" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.2 }}>
          {children}
        </motion.div>
      </AnimatePresence>
    </motion.aside>
  )
}

/** One section's title + scrolling content inside the slide-over. */
function Shell({ title, sub, children }) {
  return (
    <>
      <div className="sp-head"><div><h2>{title}</h2>{sub && <div className="mb-sub">{sub}</div>}</div></div>
      <div className="sp-scroll">{children}</div>
    </>
  )
}

export function ProfilePanel() {
  const { t } = useLang()
  return (
    <Shell title={t('Your profile')} sub={t('What others see when you ask to join')}>
      <div className="profile-hero">
        <div className="big">P</div>
        <h2 style={{ fontSize: 22 }}>Philip</h2>
        <div className="mb-sub">{t('New in Warsaw · Mokotów · speaks EN / PL')}</div>
        <div className="chips">{['music', 'running', 'theatre', 'meetups'].map((c) => <span className="badge" key={c} style={{ background: `color-mix(in srgb, ${categoryColor(c)} 15%, transparent)`, color: categoryColor(c) }}>{categoryLabel(c)}</span>)}</div>
        <p className="mb-text" style={{ marginTop: 12 }}>{t('Looking for people to go to concerts with and a squad for Sunday runs along the Vistula.')}</p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12 }}>
          <button className="btn small">Instagram</button><button className="btn small">GitHub</button><button className="btn small primary">{t('Edit profile')}</button>
        </div>
      </div>
      <div className="blk-title" style={{ padding: '0 10px' }}>{t('Join requests')}</div>
      {[['Ola', 'wants to join your picnic', 'accept'], ['Kamil', 'wants to join your run', 'accept']].map(([n, what], i) => (
        <div className="sp-row" key={i}><span className="av" style={{ background: AV[i] }}>{n[0]}</span><span><div className="t">{n}</div><div className="s">{t(what)}</div></span>
          <span className="right" style={{ display: 'flex', gap: 6 }}><button className="btn small primary">{t('Accept')}</button><button className="btn small">{t('Pass')}</button></span></div>
      ))}
      <div className="blk-title" style={{ padding: '0 10px', marginTop: 18 }}>{t('Set my location to')}</div>
      <StartPointPicker />
    </Shell>
  )
}

export function MessagesPanel() {
  const { t } = useLang()
  const msgs = [['Ola', 'See you at the boulevards at 18?', '2m'], ['Squad: Jazz Jamboree', 'Marta: I got the tickets 🎷', '1h'], ['Kamil', 'Pace 5:30 ok for you?', '3h'], ['Tomek', 'Board games Friday, bring snacks', 'yday']]
  return (
    <Shell title={t('Messages')} sub={t('Only people you met at an event')}>
      {msgs.map(([n, text, when], i) => (
        <div className="sp-row" key={i}><span className="av" style={{ background: AV[i % AV.length] }}>{n[0]}</span><span><div className="t">{n}</div><div className="s">{text}</div></span><span className="right">{when}</span></div>
      ))}
    </Shell>
  )
}

export function FavouritesPanel({ features, favourites, onPick }) {
  const { t } = useLang()
  const list = features.filter((f) => favourites.has(f.properties.event_id))
  return (
    <Shell title={t('Favourite spots')} sub={t('{n} starred · shown on the map by default', { n: list.length })}>
      {list.map((f) => {
        const p = f.properties
        return (
          <button className="sp-row" key={f.id} onClick={() => onPick(f)} style={{ width: '100%', textAlign: 'left' }}>
            <span className="av" style={{ background: categoryColor(p.categories?.[0]) }}><Star size={18} filled /></span>
            <span><div className="t">{p.title}</div><div className="s">{p.venue_name || p.address || p.district || ''}</div></span>
          </button>
        )
      })}
      {!list.length && <div className="res-empty">{t('Star places from their map box and they appear here.')}</div>}
    </Shell>
  )
}

export function SourcesPanel() {
  const { t } = useLang()
  const [sources, setSources] = useState([])
  useEffect(() => { fetchSources().then(setSources) }, [])
  const max = Math.max(1, ...sources.map((s) => s.item_count))
  return (
    <Shell title={t("APIs I'm plugged in to")} sub={t('Where every pin comes from')}>
      {sources.map((s) => (
        <div className="sp-row" key={s.slug} style={{ display: 'block' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="t">{s.name}</span>
            <span className={`badge ${s.is_reliable ? 'accent' : ''}`} style={{ marginLeft: 'auto' }}>{s.is_reliable ? t('reliable') : s.last_status || t('community')}</span>
          </div>
          <div className="s">{s.item_count.toLocaleString(locale())} {t('items')}{s.last_run_at ? ` · ${t('last run')} ${new Date(s.last_run_at).toLocaleString(locale(), { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}` : ''}</div>
          <div className="src-bar"><i style={{ width: `${(s.item_count / max) * 100}%`, background: s.is_reliable ? 'var(--accent)' : 'var(--fg-3)' }} /></div>
        </div>
      ))}
    </Shell>
  )
}
