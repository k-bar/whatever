import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { dataStatus, fetchJoinRequests, fetchSources } from '../data/api'
import { categoryColor } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { CloseButton } from './CloseButton'
import { Brand } from './Brand'
import { Burger, Expand, Shrink, Star } from './Icons'
import { MENU_CLOSED, MENU_ITEMS, MENU_OPEN, usePush } from './SearchBar'
import { StartPointPicker } from './StartPointPicker'
import { ProfilePage } from './ProfilePage'
import { LanduseLegend } from './LanduseLegend'
import { useConfig } from '../config/store'
import { DEV_TOOLS } from '../config/env'
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
  const [closedClip, setClosedClip] = useState(MENU_CLOSED) // where the burger is, so the menu grows out from under it
  const push = usePush()
  const ref = useRef(null)
  const burgerRef = useRef(null)
  const toggleMenu = () => {
    const b = burgerRef.current?.getBoundingClientRect(), menuLeft = (ref.current?.getBoundingClientRect().left ?? 0) + 14, w = 290 // .so-menu
    if (b) {
      const pct = (x) => Math.min(96, Math.max(0, (x / w) * 100)).toFixed(1)
      setClosedClip(`inset(0% ${pct(w - (b.right - menuLeft))}% 88% ${pct(b.left - menuLeft)}% round 12px)`)
    }
    setMenu(!menu)
  }
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
        <button ref={burgerRef} className={`so-burger ${menu ? 'open' : ''}`} onClick={toggleMenu} aria-label={t('Menu')} aria-expanded={menu}><Burger size={22} /></button>
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
            <motion.div className="so-menu surface" style={{ willChange: 'clip-path' }}
              initial={{ clipPath: closedClip, opacity: 0 }} animate={{ clipPath: MENU_OPEN, opacity: 1 }}
              exit={{ clipPath: closedClip, opacity: [1, 1, 0], transition: { ...push, opacity: { ...push, times: [0, 0.75, 1] } } }}
              transition={{ ...push, opacity: { duration: push.duration * 0.25, ease: 'linear' } }}>
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
function Shell({ title, sub, children, footer }) {
  return (
    <>
      <div className="sp-head"><div><h2>{title}</h2>{sub && <div className="mb-sub">{sub}</div>}</div></div>
      <div className="sp-scroll">{children}</div>
      {footer && <div className="sp-foot">{footer}</div>}
    </>
  )
}

export function ProfilePanel({ features, onPick }) {
  const { t } = useLang()
  const [requests, setRequests] = useState([])
  useEffect(() => { fetchJoinRequests().then(setRequests) }, [])
  return (
    <Shell title={t('Your profile')} sub={t('What others see when you ask to join')}>
      <ProfilePage features={features} onPick={onPick} />
      <div className="blk-title" style={{ padding: '0 10px' }}>{t('Join requests')}</div>
      {requests.map((r) => (
        <div className="sp-row" key={r.id}>
          <span className="av" style={{ background: AV[r.requester.id % AV.length] }}>{r.requester.display_name[0]}</span>
          <span><div className="t">{r.requester.display_name}</div><div className="s">{t('wants to join · {event}', { event: r.event_title })}</div></span>
          <span className="right">{fmtWhen(r.starts_at)}</span>
        </div>
      ))}
      {!requests.length && <div className="res-empty">{t('No join requests yet.')}</div>}
      <div className="blk-title" style={{ padding: '0 10px', marginTop: 18 }}>{t('Set my location to')}</div>
      <StartPointPicker />
    </Shell>
  )
}

export function MessagesPanel() {
  const { t } = useLang()
  return (
    <Shell title={t('Messages')} sub={t('Only people you met at an event')}>
      <div className="res-empty">{t('No messages yet. Once someone accepts your join request, you can talk here.')}</div>
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

/** Live / offline status of the API and how many pins are loaded (was the bottom-left map badge). */
function DataStatus({ pins }) {
  const { t } = useLang()
  return (
    <div className={`data-status ${dataStatus.source}`}>
      <i />{t(dataStatus.source === 'api' ? 'live API' : dataStatus.source === 'offline' ? 'API offline' : 'loading…')} · {pins.toLocaleString(locale())} {t('pins')}
    </div>
  )
}

/** Data sources: where every pin comes from; its footer holds the live status and the map key. */
export function SourcesPanel({ pins = 0, getMap, mobile }) {
  const { t } = useLang()
  const { values } = useConfig()
  const [sources, setSources] = useState([])
  useEffect(() => { fetchSources().then(setSources) }, [])
  const max = Math.max(1, ...sources.map((s) => s.item_count))
  return (
    <Shell title={t('Data sources')} sub={t('Where every pin comes from')}
      footer={<>{DEV_TOOLS && values.apiBadge && <DataStatus pins={pins} />}<LanduseLegend embedded getMap={getMap} mobile={mobile} /></>}>
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
