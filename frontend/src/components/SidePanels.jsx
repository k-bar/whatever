import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { dataStatus, fetchJoinRequests, fetchSources, onAuthChange } from '../data/api'
import { categoryColor } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { Brand } from './Brand'
import { ChevronL, ChevronR, Cog, Expand, Mermaid, Message, Plus, Shrink, Silhouette, Star, X } from './Icons'
import { StartPointPicker } from './StartPointPicker'
import { ProfilePage } from './ProfilePage'
import { LanduseLegend } from './LanduseLegend'
import { useConfig } from '../config/store'
import { DEV_TOOLS } from '../config/env'
import { PIN_GROUPS } from '../data/pinGroups'
import { CITY_LAYERS } from './cityLayers'
import { locale, useLang } from '../i18n'
import { useMe, VerifyBanner } from './Account'
import { EventChat } from './EventChat'
import { assetUrl } from '../data/api'

const AV = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']

/** The tray's home: what used to be the burger pop-up. "create" starts a new event instead of opening a view. */
const TRAY_ITEMS = [
  { id: 'selects', label: 'Syrenka Selects', hint: 'Picked for the next two weeks', tone: 'logo', icon: <Mermaid size={30} /> },
  { id: 'create', label: 'Create event', hint: 'Host something, invite people', tone: 'create', icon: <Plus size={22} stroke={2.6} /> },
  { id: 'profile', label: 'Profile', hint: 'You, your friends and events', tone: 'profile', icon: <Silhouette size={22} /> },
  { id: 'messages', label: 'Messages', hint: 'Event chats you follow', tone: 'messages', icon: <Message size={21} stroke={2.2} /> },
  { id: 'settings', label: 'Settings', hint: 'Data sources and the map key', tone: 'settings', icon: <Cog size={21} stroke={2} /> },
]

function TrayMenu({ onSection, unread = 0 }) {
  const { t } = useLang()
  return (
    <nav className="tray-menu" aria-label={t('Menu')}>
      {TRAY_ITEMS.map((it) => (
        <button key={it.id} className="tray-item" onClick={() => onSection(it.id)}>
          <span className={`tray-ic ${it.tone}`}>{it.icon}</span>
          <span className="tray-txt"><b>{t(it.label)}</b><small>{t(it.hint)}</small></span>
          {it.id === 'messages' && unread > 0 && <span className="tray-badge" aria-label={t('{n} unread', { n: unread })}>{unread > 99 ? '99+' : unread}</span>}
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
export function SlideOver({ section, onSection, onBack, onClose, full, onFull, onHome, mobile, unread, children }) {
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
          {atHome ? <TrayMenu onSection={onSection} unread={unread} /> : (
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

export function ProfilePanel({ features, onPick, onFavourites, person }) {
  const { t } = useLang()
  const me = useMe()
  const [other, setOther] = useState(false) // looking at someone else's profile (a friend, a person on the map)
  const [requests, setRequests] = useState([])
  useEffect(() => { const load = () => fetchJoinRequests().then(setRequests); load(); return onAuthChange(load) }, [])
  return (
    <Shell title={t(other ? 'Profile' : 'Your profile')} sub={other ? null : t('What others see when you ask to join')}>
      {!other && <VerifyBanner me={me} />}
      <ProfilePage features={features} onPick={onPick} person={person} onViewing={setOther} />
      {!other && <>{/* my own things, not under someone else's profile */}
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
      </>}
    </Shell>
  )
}

/**
 * Messages: the event chats I follow (posted in, host, or followed), newest activity first, with
 * unread counts; or one chat when `chat` is set. Opening a chat from a map box lands here too.
 */
export function MessagesPanel({ chats, chat, onOpenChat, onOpenEvent, onOpenUser }) {
  const { t } = useLang()
  if (chat) return <EventChat key={`${chat.kind}:${chat.id}`} target={chat} onBack={() => onOpenChat(null)} onOpenEvent={onOpenEvent} onOpenUser={onOpenUser} />
  const list = chats.chats
  return (
    <Shell title={t('Messages')} sub={t('Chats of events you follow')}>
      {list === null && <div className="res-empty">{t('Loading…')}</div>}
      {list?.map((c) => (
        <button key={c.key} className={`sp-row chat-row ${c.unread ? 'unread' : ''}`} onClick={() => onOpenChat({ kind: c.kind, id: c.target_id })}>
          <span className="av" style={c.image_url ? { background: `center / cover url(${assetUrl(c.image_url)})` } : { background: AV[c.target_id % AV.length] }}>{!c.image_url && c.title[0]}</span>
          <span className="chat-row-txt">
            <div className="t">{c.title}</div>
            <div className="s">{c.last_message
              ? `${c.last_message.user.display_name}: ${c.last_message.deleted ? t('Message deleted') : c.last_message.body}`
              : c.starts_at ? fmtWhen(c.starts_at) : t('No messages yet')}</div>
          </span>
          {c.unread > 0 ? <span className="right tray-badge">{c.unread > 99 ? '99+' : c.unread}</span> : c.last_message_at && <span className="right">{fmtWhen(c.last_message_at)}</span>}
        </button>
      ))}
      {list?.length === 0 && <div className="res-empty">{t('No chats yet. Open an event on the map and tap Chat to talk with people going.')}</div>}
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

/**
 * Data sources: how many of each thing is on the map, where every pin comes from; its footer holds the
 * live status and the map key. (The toolbar's pin box only switches them on and off.)
 */
export function SettingsPanel({ pins = 0, pinCounts = {}, cityCounts = {}, getMap, mobile }) {
  const { t } = useLang()
  const { values } = useConfig()
  const [sources, setSources] = useState([])
  useEffect(() => { fetchSources().then(setSources) }, [])
  const max = Math.max(1, ...sources.map((s) => s.item_count))
  return (
    <Shell title={t('Settings')} sub={t('Data sources and the map key')}
      footer={<>{DEV_TOOLS && values.apiBadge && <DataStatus pins={pins} />}<LanduseLegend embedded getMap={getMap} mobile={mobile} /></>}>
      <div className="blk-title so-section">{t('On the map')}<span>{t('How many of each there are right now')}</span></div>
      <div className="so-counts">
        {[...PIN_GROUPS.map((g) => [g, pinCounts[g.id]]), ...CITY_LAYERS.map((l) => [l, cityCounts[l.id]])].map(([o, n]) => (
          <div className={`so-count ${values[o.param] === false ? 'off' : ''}`} key={o.id}>
            <span aria-hidden="true">{o.emoji}</span><span className="t">{t(o.label)}</span>
            <b>{n == null ? '–' : n.toLocaleString(locale())}</b>
          </div>
        ))}
      </div>
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
