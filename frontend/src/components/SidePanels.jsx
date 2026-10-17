import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { dataStatus, fetchJoinRequests, fetchSources } from '../data/api'
import { categoryColor } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { Brand } from './Brand'
import { ChevronL, ChevronR, Cog, Expand, Mermaid, Message, Plus, Shrink, Silhouette, Star, X } from './Icons'
import { StartPointPicker } from './StartPointPicker'
import { ProfilePage } from './ProfilePage'
import { LanduseLegend } from './LanduseLegend'
import { useConfig } from '../config/store'
import { locale, useLang } from '../i18n'

const AV = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']

/** The tray's home: what used to be the burger pop-up. "create" starts a new event instead of opening a view. */
const TRAY_ITEMS = [
  { id: 'selects', label: 'Syrenka Selects', hint: 'Picked for the next two weeks', tone: 'logo', icon: <Mermaid size={30} /> },
  { id: 'create', label: 'Create event', hint: 'Host something, invite people', tone: 'create', icon: <Plus size={22} stroke={2.6} /> },
  { id: 'profile', label: 'Profile', hint: 'You, your friends and events', tone: 'profile', icon: <Silhouette size={22} /> },
  { id: 'messages', label: 'Messages', hint: 'People you met at events', tone: 'messages', icon: <Message size={21} stroke={2.2} /> },
  { id: 'settings', label: 'Settings', hint: 'Data sources and the map key', tone: 'settings', icon: <Cog size={21} stroke={2} /> },
]

function TrayMenu({ onSection }) {
  const { t } = useLang()
  return (
    <nav className="tray-menu" aria-label={t('Menu')}>
      {TRAY_ITEMS.map((it) => (
        <button key={it.id} className="tray-item" onClick={() => onSection(it.id)}>
          <span className={`tray-ic ${it.tone}`}>{it.icon}</span>
          <span className="tray-txt"><b>{t(it.label)}</b><small>{t(it.hint)}</small></span>
          {it.id !== 'create' && <ChevronR size={18} className="tray-go" />}
        </button>
      ))}
    </nav>
  )
}

/**
 * The slide-over tray: a full-height section on the left, "under" the map. The search bar's burger opens and
 * closes it (and turns into its (x)). Two positions: the menu (home) and inside one item, with a way back.
 * The bar has the logo (back to the start page) and maximise; on a phone or maximised, the search bar is
 * covered, so the (x) moves into the bar's corner.
 */
export function SlideOver({ section, onSection, onBack, onClose, full, onFull, onHome, mobile, children }) {
  const { t } = useLang()
  const atHome = section === 'menu'
  return (
    <motion.aside className={`slideover ${full || mobile ? 'full' : ''}`} initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }}
      transition={{ type: 'spring', stiffness: 260, damping: 34 }}>
      <header className="so-bar">
        {(full || mobile) && <button className="btn icon so-close" onClick={onClose} aria-label={t('Close menu')}><X size={22} stroke={2.2} /></button>}
        <Brand onHome={onHome} />
        <div className="so-actions">
          {!mobile && (
            <button className="btn icon so-expand" onClick={onFull} aria-label={t(full ? 'Shrink' : 'Full screen')} title={t(full ? 'Shrink' : 'Full screen')}>
              {full ? <Shrink size={18} stroke={2.2} /> : <Expand size={18} stroke={2.2} />}
            </button>
          )}
        </div>
      </header>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={section} className="so-body" initial={{ opacity: 0, x: atHome ? -16 : 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: atHome ? -16 : 16 }} transition={{ duration: 0.2 }}>
          {atHome ? <TrayMenu onSection={onSection} /> : (
            <>
              <button className="so-back" onClick={onBack}><ChevronL size={18} stroke={2.2} />{t('Menu')}</button>
              {children}
            </>
          )}
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

export function ProfilePanel({ features, onPick, onFavourites }) {
  const { t } = useLang()
  const [requests, setRequests] = useState([])
  useEffect(() => { fetchJoinRequests().then(setRequests) }, [])
  return (
    <Shell title={t('Your profile')} sub={t('What others see when you ask to join')}>
      <ProfilePage features={features} onPick={onPick} />
      {onFavourites && (
        <button className="sp-row so-link" onClick={onFavourites}>
          <span className="av" style={{ background: '#f2a900' }}><Star size={18} filled /></span>
          <span><div className="t">{t('Favourite spots')}</div><div className="s">{t('Places and events you starred')}</div></span>
          <ChevronR size={18} className="right" />
        </button>
      )}
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
export function SettingsPanel({ pins = 0, getMap, mobile }) {
  const { t } = useLang()
  const { values } = useConfig()
  const [sources, setSources] = useState([])
  useEffect(() => { fetchSources().then(setSources) }, [])
  const max = Math.max(1, ...sources.map((s) => s.item_count))
  return (
    <Shell title={t('Settings')} sub={t('Data sources and the map key')}
      footer={<>{values.apiBadge && <DataStatus pins={pins} />}<LanduseLegend embedded getMap={getMap} mobile={mobile} /></>}>
      <div className="blk-title so-section">{t('Data sources')}<span>{t('Where every pin comes from')}</span></div>
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
