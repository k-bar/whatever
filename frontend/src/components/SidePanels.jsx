import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { LoginRequired, assetUrl, fetchJoinRequests, fetchMe, fetchSources, logout, onAuthChange, updateMe } from '../data/api'
import { CATEGORIES, categoryColor, categoryLabel } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { CloseButton } from './CloseButton'
import { Brand } from './Brand'
import { Burger, Expand, Shrink, Star } from './Icons'
import { MENU_ITEMS } from './SearchBar'
import { StartPointPicker } from './StartPointPicker'
import { LoginForm } from './LoginForm'
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

const catBadge = (c) => ({ background: `color-mix(in srgb, ${categoryColor(c)} 15%, transparent)`, color: categoryColor(c) })
const GENDER = { 'mężczyzna': 'Man', 'kobieta': 'Woman' } // people.db stores gender in Polish
const jsonList = (v) => { if (Array.isArray(v)) return v; try { const a = JSON.parse(v); return Array.isArray(a) ? a : [] } catch { return [] } }

/**
 * Your profile, laid out like a row of backend/db/people.db (table ludzie): personal details, favourite
 * places, events you are going to / have been to. GET /me returns display_name, bio, photos, interests,
 * links, email, created_at; the people.db-only fields (first_name, username, age, ...) show once /me
 * returns them, "—" until then. Edit -> PATCH /me with the fields the API accepts.
 */
export function ProfilePanel() {
  const { t } = useLang()
  const [me, setMe] = useState(undefined) // undefined = loading, null = no account in this browser yet
  const [requests, setRequests] = useState([])
  const [editing, setEditing] = useState(false)
  const load = () => { fetchMe().then(setMe); fetchJoinRequests().then(setRequests) }
  useEffect(() => { load(); return onAuthChange(load) }, [])
  const name = me?.display_name || t('Guest')
  const photo = me?.photos?.[0]
  return (
    <Shell title={t('Your profile')} sub={t('What others see when you ask to join')}>
      {me === undefined && <div className="res-empty">{t('Loading…')}</div>}
      {me === null && (
        <div className="profile-hero">
          <div className="big">{name[0]}</div>
          <h2 style={{ fontSize: 22 }}>{name}</h2>
          <p className="mb-text" style={{ margin: '8px 0 14px' }}>{t('No profile yet. It is created the first time you post an event or ask to join one.')}</p>
          <div style={{ textAlign: 'left' }}><LoginForm onDone={load} /></div>
        </div>
      )}
      {me && editing && <ProfileEditor me={me} onCancel={() => setEditing(false)} onSaved={(m) => { setMe(m); setEditing(false) }} />}
      {me && !editing && (
        <>
          <div className="profile-hero">
            <div className="big" style={photo ? { backgroundImage: `url(${assetUrl(photo)})`, backgroundSize: 'cover' } : {}}>{!photo && name[0]}</div>
            <h2 style={{ fontSize: 22 }}>{name}</h2>
            {me.username && <div className="mb-sub">{me.username}</div>}
            {me.interests?.length > 0 && (
              <div className="chips">{me.interests.map((c) => <span className="badge" key={c} style={catBadge(c)}>{categoryLabel(c)}</span>)}</div>
            )}
            {me.bio && <p className="mb-text" style={{ marginTop: 12 }}>{me.bio}</p>}
            {me.links && Object.keys(me.links).length > 0 && (
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12, flexWrap: 'wrap' }}>
                {Object.entries(me.links).map(([label, url]) => <a key={label} className="btn small" href={url} target="_blank" rel="noreferrer">{label}</a>)}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 14 }}>
              <button className="btn small primary" onClick={() => setEditing(true)}>{t('Edit profile')}</button>
              <button className="btn small" onClick={() => { logout(); setMe(null); setRequests([]) }}>{t('Log out')}</button>
            </div>
          </div>
          <ProfileDetails me={me} />
        </>
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

/** The people.db columns of my profile: personal details, then places and events as lists. */
function ProfileDetails({ me }) {
  const { t } = useLang()
  const [first, ...rest] = (me.display_name || '').split(' ')
  const since = me.created_at ? new Date(me.created_at).toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: 'numeric' }) : null
  const rows = [
    ['First name', me.first_name ?? first],
    ['Last name', me.second_name ?? rest.join(' ')],
    ['Username', me.username],
    ['Email', me.email],
    ['Age', me.age],
    ['Gender', me.gender && t(GENDER[me.gender] || me.gender)],
    ['Member since', since],
  ]
  const lists = [
    ['Favourite places', jsonList(me.favourite_locations), 'No favourite places yet.'],
    ['Going to', jsonList(me.events_going_to), 'Not going anywhere yet.'],
    ['Been to', jsonList(me.events_been_to), 'No past events yet.'],
  ]
  return (
    <div className="profile-details">
      <div className="blk-title">{t('Personal details')}</div>
      <dl className="profile-grid">
        {rows.map(([label, value]) => (
          <div key={label}><dt>{t(label)}</dt><dd>{value === undefined || value === null || value === '' ? '—' : value}</dd></div>
        ))}
      </dl>
      {lists.map(([label, items, empty]) => (
        <div key={label} style={{ marginTop: 16 }}>
          <div className="blk-title">{t(label)}</div>
          {items.length ? <div className="chips" style={{ justifyContent: 'flex-start' }}>{items.map((x) => <span className="badge" key={x}>{x}</span>)}</div>
            : <div className="mb-text muted">{t(empty)}</div>}
        </div>
      ))}
    </div>
  )
}

const isUrl = (s) => /^https?:\/\/\S+$/i.test(s)

/** Edit what PATCH /me accepts: name, bio, main photo, interests, links. */
function ProfileEditor({ me, onCancel, onSaved }) {
  const { t } = useLang()
  const [name, setName] = useState(me.display_name || '')
  const [bio, setBio] = useState(me.bio || '')
  const [photo, setPhoto] = useState(me.photos?.[0] || '')
  const [interests, setInterests] = useState(new Set(me.interests || []))
  const [links, setLinks] = useState(() => [...Object.entries(me.links || {}), ['', '']])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const toggle = (c) => setInterests((s) => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n })
  const setLink = (i, j) => (e) => setLinks((ls) => {
    const n = ls.map((l, k) => (k === i ? (j ? [l[0], e.target.value] : [e.target.value, l[1]]) : l))
    return n[n.length - 1].some(Boolean) ? [...n, ['', '']] : n // always one empty row at the end
  })
  const filled = links.filter(([l, u]) => l.trim() || u.trim())
  const problem = !name.trim() ? 'Enter your name'
    : photo && !isUrl(photo) ? 'The photo must be a link starting with http(s)://'
      : filled.some(([l, u]) => !l.trim() || !isUrl(u.trim())) ? 'Each link needs a name and an address starting with http(s)://'
        : null

  const save = async (e) => {
    e.preventDefault()
    if (problem || saving) return
    setSaving(true); setError(null)
    try {
      const photos = photo ? [photo, ...(me.photos || []).slice(1)] : (me.photos || []).slice(1)
      onSaved(await updateMe({
        display_name: name.trim(), bio: bio.trim() || null, photos,
        interests: [...interests], links: Object.fromEntries(filled.map(([l, u]) => [l.trim(), u.trim()])),
      }))
    } catch (err) {
      setError(err instanceof LoginRequired ? 'Log in to continue' : 'Could not save. Try again.')
      setSaving(false)
    }
  }

  return (
    <form className="profile-edit" onSubmit={save}>
      <label className="ce-field"><span className="ce-label">{t('Your name')}</span>
        <input className="ce-input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
      <label className="ce-field"><span className="ce-label">{t('About me')}</span>
        <textarea className="ce-input" value={bio} maxLength={2000} onChange={(e) => setBio(e.target.value)} placeholder={t('A few words others see when you ask to join')} /></label>
      <label className="ce-field"><span className="ce-label">{t('Photo (link)')}</span>
        <input className="ce-input" value={photo} onChange={(e) => setPhoto(e.target.value.trim())} placeholder="https://…" /></label>
      <div className="ce-field"><span className="ce-label">{t('Interests')}</span>
        <div className="chips" style={{ justifyContent: 'flex-start' }}>
          {Object.keys(CATEGORIES).map((c) => (
            <button type="button" key={c} className={`badge profile-chip ${interests.has(c) ? 'on' : ''}`} style={interests.has(c) ? catBadge(c) : {}} onClick={() => toggle(c)} aria-pressed={interests.has(c)}>
              {categoryLabel(c)}
            </button>
          ))}
        </div>
      </div>
      <div className="ce-field"><span className="ce-label">{t('Links')}</span>
        {links.map(([l, u], i) => (
          <div className="ce-row" key={i} style={{ marginBottom: 6 }}>
            <input className="ce-input" style={{ flex: '0 0 34%' }} value={l} onChange={setLink(i, 0)} placeholder={t('e.g. Instagram')} />
            <input className="ce-input" value={u} onChange={setLink(i, 1)} placeholder="https://…" />
          </div>
        ))}
      </div>
      {(error || problem) && <div className="mb-text" style={{ color: error ? 'var(--accent)' : 'var(--fg-3)', marginBottom: 10 }}>{t(error || problem)}</div>}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" className="btn small" onClick={onCancel}>{t('Cancel')}</button>
        <button type="submit" className="btn small primary" disabled={Boolean(problem) || saving}>{t(saving ? 'One moment…' : 'Save')}</button>
      </div>
    </form>
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
