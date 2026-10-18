import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import {
  answerFriendRequest, assetUrl, checkUsername, fetchFriendRequests, fetchFriends, fetchMe, fetchProfile, fetchProfileEvents,
  isLoggedIn, logout, onAuthChange, searchPeople, sendFriendRequest, unfriend, updateMe, uploadProfilePhoto,
} from '../data/api'
import { CATEGORIES, categoryColor, categoryLabel } from '../data/categories'
import { fmtWhenFor } from '../mapboxes/curate'
import { locale, useLang } from '../i18n'
import { Check, ChevronL, Photo, Pin, Plus, Search, UserCheck, X } from './Icons'
import { LoginForm } from './LoginForm'

/**
 * The "mini Facebook" profile: @username, Friends · Been to · Hosted, "You can find me at …",
 * and tabs for going / been to / hosting / friends. Polish labels follow the person's gender
 * (Byłam / Byłem, Inicjatorka / Inicjator); without one we use the neutral "Byłem/am".
 */
function labels(lang, gender) {
  if (lang !== 'pl') return { friends: 'Friends', been: 'Been to', hosted: 'Hosted', going: 'Going', hosting: 'Hosting' }
  return {
    friends: 'Znajomi',
    been: { f: 'Byłam', m: 'Byłem' }[gender] || 'Byłem/am',
    hosted: { f: 'Inicjatorka', m: 'Inicjator' }[gender] || 'Inicjator/ka',
    going: 'Idę',
    hosting: 'Organizuję',
  }
}

const AV = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']
export function Avatar({ user, size = 44 }) {
  const photo = user?.photos?.[0]
  const letter = (user?.display_name || '?')[0].toUpperCase()
  return (
    <span className="pp-av" style={{ width: size, height: size, fontSize: size * 0.42, background: photo ? `center / cover url(${assetUrl(photo)})` : AV[(user?.id || 0) % AV.length] }}>
      {!photo && letter}
    </span>
  )
}

/** Profile area of the slide-over: me by default; tapping a friend opens theirs (with a way back). */
export function ProfilePage({ features, onPick, person, onViewing }) {
  const { t } = useLang()
  const [meId, setMeId] = useState(undefined) // undefined = loading, null = logged out
  const [viewing, setViewing] = useState(null) // another person's id, null = me
  const [editing, setEditing] = useState(false)
  const [rev, setRev] = useState(0) // bump to reload after edits / friend changes
  const personRef = useRef(person) // someone tapped on the map: open on them, not on me
  personRef.current = person

  useEffect(() => {
    const load = () => fetchMe().then((m) => { setMeId(m ? m.id : null); setViewing(personRef.current?.id ?? null); setEditing(false) })
    load()
    return onAuthChange(load)
  }, [])
  useEffect(() => { if (person) { setViewing(person.id); setEditing(false) } }, [person])
  useEffect(() => { onViewing?.(viewing != null && viewing !== meId) }, [viewing, meId, onViewing])

  if (meId === undefined) return <div className="res-empty">{t('Loading…')}</div>
  if (meId === null && viewing == null) {
    return <div className="pp-loggedout"><p>{t('Log in to get your profile: an @username, friends, and the events you go to and host.')}</p><LoginForm /></div>
  }
  const userId = viewing ?? meId
  return (
    <div className="pp">
      {viewing != null && viewing !== meId && meId && (
        <button className="btn text small pp-back" onClick={() => setViewing(null)}><ChevronL size={16} /> {t('Back to my profile')}</button>
      )}
      {editing
        ? <EditProfile features={features} onDone={() => { setEditing(false); setRev((r) => r + 1) }} />
        : <ProfileView key={userId} userId={userId} rev={rev} onEdit={() => setEditing(true)} onOpenUser={(id) => setViewing(id === meId ? null : id)}
            onChanged={() => setRev((r) => r + 1)} onPick={onPick} features={features} />}
    </div>
  )
}

function ProfileView({ userId, rev, onEdit, onOpenUser, onChanged, onPick, features }) {
  const { t, lang } = useLang()
  const [p, setP] = useState(null)
  const [err, setErr] = useState(null)
  const [tab, setTab] = useState('going')
  // rev: refetch in place after edits / friend changes, so the open tab stays put
  useEffect(() => { fetchProfile(userId).then(setP).catch((e) => setErr(e.message)) }, [userId, rev])
  if (err) return <div className="res-empty">{err}</div>
  if (!p) return <div className="res-empty">{t('Loading…')}</div>

  const L = labels(lang, p.gender)
  const isMe = p.relation === 'self'
  const tabs = [['going', L.going], ['been', L.been], ['hosting', L.hosting], ['friends', L.friends]]
  return (
    <>
      <div className="pp-head">
        <Avatar user={p} size={76} />
        <div className="pp-names">
          <h2>{p.display_name}</h2>
          <div className="pp-user">@{p.username}</div>
          {isMe
            ? <span style={{ display: 'flex', gap: 8 }}><button className="btn small" onClick={onEdit}>{t('Edit profile')}</button><button className="btn small" onClick={logout}>{t('Log out')}</button></span>
            : <FriendButton profile={p} onChanged={onChanged} />}
        </div>
      </div>

      <div className="pp-stats">
        <button onClick={() => p.can_see_events && setTab('friends')}><b>{p.stats.friends}</b><span>{L.friends}</span></button>
        <button onClick={() => p.can_see_events && setTab('been')}><b>{p.stats.been_to}</b><span>{L.been}</span></button>
        <button onClick={() => p.can_see_events && setTab('hosting')}><b>{p.stats.hosted}</b><span>{L.hosted}</span></button>
      </div>

      {p.bio && <p className="pp-bio">{p.bio}</p>}
      {p.interests?.length > 0 && (
        <div className="chips pp-chips">{p.interests.map((c) => <span className="badge" key={c} style={{ background: `color-mix(in srgb, ${categoryColor(c)} 15%, transparent)`, color: categoryColor(c) }}>{categoryLabel(c)}</span>)}</div>
      )}
      {p.hangouts?.length > 0 && (
        <div className="pp-hangouts">
          <span className="lbl">{t('You can find me at')}</span>
          {p.hangouts.map((h) => {
            const f = h.place_id && features?.find((x) => x.properties.event_id === h.place_id)
            return <button key={h.name} className="pp-place" disabled={!f} onClick={() => f && onPick?.(f)}><Pin size={13} />{h.name}</button>
          })}
        </div>
      )}

      {isMe && <PersonalDetails gender={p.gender} />}

      {p.can_see_events ? (
        <>
          <div className="pp-tabs" role="tablist">
            {tabs.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{label}</button>)}
          </div>
          {tab === 'friends'
            ? <FriendsTab userId={p.id} isMe={isMe} onOpenUser={onOpenUser} onChanged={onChanged} />
            : <EventsTab key={tab} userId={p.id} scope={tab} isMe={isMe} onPick={onPick} features={features} />}
        </>
      ) : (
        <div className="res-empty">{t('Become friends to see the events {name} goes to.', { name: p.display_name })}</div>
      )}
    </>
  )
}

/** My private details from GET /me: first / last name, age, gender, email, member since. Only on my own profile. */
function PersonalDetails({ gender }) {
  const { t } = useLang()
  const [me, setMe] = useState(null)
  useEffect(() => { fetchMe().then(setMe) }, [])
  if (!me) return null
  const sex = me.gender ?? gender
  const rows = [
    ['First name', me.first_name],
    ['Last name', me.last_name],
    ['Age', me.age],
    ['Gender', sex && t({ f: 'Woman', m: 'Man' }[sex])],
    ['Email', me.email],
    ['Member since', me.created_at && new Date(me.created_at).toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: 'numeric' })],
  ]
  return (
    <div className="pp-details">
      <span className="lbl">{t('Personal details')}</span>
      <dl>
        {rows.map(([label, value]) => <div key={label}><dt>{t(label)}</dt><dd>{value || value === 0 ? value : '—'}</dd></div>)}
      </dl>
    </div>
  )
}

function FriendButton({ profile, onChanged }) {
  const { t } = useLang()
  const [busy, setBusy] = useState(false)
  const act = async (fn) => { setBusy(true); try { await fn(); onChanged() } catch (e) { window.dispatchEvent(new CustomEvent('syrenka:toast', { detail: e.message })) } finally { setBusy(false) } }
  if (!isLoggedIn()) return null
  const rel = profile.relation
  if (rel === 'friends') return <button className="btn small" disabled={busy} onClick={() => act(() => unfriend(profile.id))} title={t('Remove friend')}><UserCheck size={15} /> {t('Friends')}</button>
  if (rel === 'request_sent') return <button className="btn small" disabled={busy} onClick={() => act(() => unfriend(profile.id))}>{t('Requested · cancel')}</button>
  if (rel === 'request_received') return <button className="btn small primary" disabled={busy} onClick={() => act(() => sendFriendRequest(profile.username))}><Check size={15} /> {t('Accept friend request')}</button>
  return <button className="btn small primary" disabled={busy} onClick={() => act(() => sendFriendRequest(profile.username))}><Plus size={15} /> {t('Add friend')}</button>
}

function EventsTab({ userId, scope, isMe, onPick, features }) {
  const { t } = useLang()
  const [list, setList] = useState(null)
  useEffect(() => { fetchProfileEvents(userId, scope).then(setList).catch(() => setList([])) }, [userId, scope])
  if (!list) return <div className="res-empty">{t('Loading…')}</div>
  if (!list.length) {
    const empty = { going: isMe ? "Nothing planned yet. Tap “I'm going” on an event." : 'Nothing planned yet.', been: 'No past events yet.', hosting: isMe ? 'Nothing to host yet. Use “+ Create event”.' : 'Not hosting anything yet.' }
    return <div className="res-empty">{t(empty[scope])}</div>
  }
  return (
    <div className="pp-events">
      {list.map((e) => {
        const f = e.event_id && features?.find((x) => x.properties.event_id === e.event_id)
        return (
          <button key={`${e.event_id}:${e.occurrence_id}:${e.user_event_id}`} className="pp-event" disabled={!f} onClick={() => f && onPick?.(f)}>
            <span className="thumb" style={e.image_url ? { backgroundImage: `url(${assetUrl(e.image_url)})` } : { background: categoryColor(e.category) }} />
            <span className="txt"><span className="t">{e.title}</span><span className="s">{fmtWhenFor(e)}{e.venue_name ? ` · ${e.venue_name}` : ''}</span></span>
          </button>
        )
      })}
    </div>
  )
}

function FriendsTab({ userId, isMe, onOpenUser, onChanged }) {
  const { t } = useLang()
  const [friends, setFriends] = useState(null)
  const [incoming, setIncoming] = useState([])
  const [outgoing, setOutgoing] = useState([])
  const reload = () => {
    fetchFriends(userId).then(setFriends).catch(() => setFriends([]))
    if (isMe) { fetchFriendRequests('incoming').then(setIncoming).catch(() => {}); fetchFriendRequests('outgoing').then(setOutgoing).catch(() => {}) }
  }
  useEffect(reload, [userId, isMe]) // eslint-disable-line react-hooks/exhaustive-deps
  const answer = async (id, status) => { await answerFriendRequest(id, status); reload(); onChanged() }

  return (
    <div className="pp-friends">
      {isMe && <AddFriend onSent={reload} />}
      {isMe && incoming.length > 0 && <>
        <div className="blk-title">{t('Friend requests')}</div>
        {incoming.map((r) => (
          <div className="sp-row" key={r.id}>
            <button className="pp-person" onClick={() => onOpenUser(r.user.id)}><Avatar user={r.user} /><span><div className="t">{r.user.display_name}</div><div className="s">@{r.user.username}</div></span></button>
            <span className="right" style={{ display: 'flex', gap: 6 }}>
              <button className="btn small primary" onClick={() => answer(r.id, 'accepted')}>{t('Accept')}</button>
              <button className="btn small" onClick={() => answer(r.id, 'declined')}>{t('Decline')}</button>
            </span>
          </div>
        ))}
      </>}
      {isMe && outgoing.length > 0 && <div className="pp-pending">{t('Waiting for: {names}', { names: outgoing.map((r) => `@${r.user.username}`).join(', ') })}</div>}
      {friends === null && <div className="res-empty">{t('Loading…')}</div>}
      {friends?.length === 0 && <div className="res-empty">{t(isMe ? 'No friends yet. Find people by their @username above.' : 'No friends yet.')}</div>}
      {friends?.map((u) => (
        <button className="sp-row pp-person" key={u.id} onClick={() => onOpenUser(u.id)}>
          <Avatar user={u} /><span><div className="t">{u.display_name}</div><div className="s">@{u.username}</div></span>
        </button>
      ))}
    </div>
  )
}

function AddFriend({ onSent }) {
  const { t } = useLang()
  const [q, setQ] = useState('')
  const [hits, setHits] = useState([])
  const [sent, setSent] = useState({})
  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return }
    const timer = setTimeout(() => searchPeople(q.trim()).then(setHits).catch(() => setHits([])), 250)
    return () => clearTimeout(timer)
  }, [q])
  const add = async (u) => {
    try { const r = await sendFriendRequest(u.username); setSent((s) => ({ ...s, [u.id]: r.status })); onSent() } catch (e) { window.dispatchEvent(new CustomEvent('syrenka:toast', { detail: e.message })) }
  }
  return (
    <div className="pp-add">
      <label className="start-input"><Search size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Add friends: search @username or name')} /></label>
      {hits.map((u) => (
        <div className="sp-row" key={u.id}>
          <Avatar user={u} size={36} /><span><div className="t">{u.display_name}</div><div className="s">@{u.username}</div></span>
          <span className="right">
            {sent[u.id] ? <span className="badge accent">{t(sent[u.id] === 'accepted' ? 'Friends' : 'Request sent')}</span>
              : <button className="btn small primary" onClick={() => add(u)}><Plus size={14} /> {t('Add')}</button>}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ---------- edit ---------- */

function EditProfile({ features, onDone }) {
  const { t } = useLang()
  const spring = useSpring()
  const [me, setMe] = useState(null)
  const [v, setV] = useState(null)
  const [name, setName] = useState({ state: 'same' }) // same | checking | ok | bad
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => { fetchMe().then((m) => { setMe(m); setV({ display_name: m.display_name, username: m.username, gender: m.gender || '', first_name: m.first_name || '', last_name: m.last_name || '', age: m.age ?? '', bio: m.bio || '', interests: m.interests || [], hangouts: m.hangouts || [], photos: m.photos || [] }) }) }, [])

  useEffect(() => {
    if (!v || !me) return
    const u = v.username.trim().replace(/^@/, '').toLowerCase()
    if (u === me.username) { setName({ state: 'same' }); return }
    setName({ state: 'checking' })
    const timer = setTimeout(() => checkUsername(u).then((r) => setName(r.available ? { state: 'ok' } : { state: 'bad', reason: r.reason })).catch(() => setName({ state: 'same' })), 350)
    return () => clearTimeout(timer)
  }, [v?.username]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!v) return <div className="res-empty">{t('Loading…')}</div>
  const set = (k, val) => setV((x) => ({ ...x, [k]: val }))
  const badAge = v.age !== '' && (Number(v.age) < 13 || Number(v.age) > 120)
  const save = async () => {
    setSaving(true); setError(null)
    const age = v.age === '' ? null : Number(v.age)
    try { await updateMe({ ...v, username: v.username.trim().replace(/^@/, ''), bio: v.bio.trim() || null, first_name: v.first_name.trim() || null, last_name: v.last_name.trim() || null, age }); onDone() } catch (e) { setError(e.message) } finally { setSaving(false) }
  }
  return (
    <motion.div className="pp-edit" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
      <PhotoField user={{ ...me, display_name: v.display_name, photos: v.photos }} onChange={(photos) => set('photos', photos)} onError={setError} />
      <label className="pp-field"><span>{t('Name')}</span><input value={v.display_name} maxLength={80} onChange={(e) => set('display_name', e.target.value)} /></label>
      <label className="pp-field">
        <span>{t('Username')}</span>
        <div className={`pp-at ${name.state}`}>@<input value={v.username.replace(/^@/, '')} maxLength={30} autoCapitalize="none" spellCheck={false} onChange={(e) => set('username', e.target.value)} />
          {name.state === 'ok' && <Check size={16} />}{name.state === 'bad' && <X size={16} />}</div>
        <small className={name.state === 'bad' ? 'bad' : ''}>{name.state === 'bad' ? t(name.reason) : name.state === 'ok' ? t('Available') : name.state === 'checking' ? t('Checking…') : t('Letters, digits, dots and underscores')}</small>
      </label>
      <div className="pp-row">
        <label className="pp-field"><span>{t('First name')}</span><input value={v.first_name} maxLength={40} autoComplete="given-name" onChange={(e) => set('first_name', e.target.value)} /></label>
        <label className="pp-field"><span>{t('Last name')}</span><input value={v.last_name} maxLength={60} autoComplete="family-name" onChange={(e) => set('last_name', e.target.value)} /></label>
      </div>
      <label className="pp-field pp-age">
        <span>{t('Age')}</span>
        <input type="number" inputMode="numeric" min={13} max={120} value={v.age} onChange={(e) => set('age', e.target.value.replace(/\D/g, '').slice(0, 3))} />
        {badAge && <small className="bad">{t('Age must be between 13 and 120')}</small>}
      </label>
      <label className="pp-field">
        <span>{t('Gender')}</span>
        <select className="pp-select" value={v.gender} onChange={(e) => set('gender', e.target.value)}>
          <option value="f">{t('Woman')}</option>
          <option value="m">{t('Man')}</option>
          <option value="">{t('Prefer not to say')}</option>
        </select>
        <small>{t('Used for Polish words on your profile, like Byłam / Byłem.')}</small>
      </label>
      <label className="pp-field"><span>{t('About me')}</span><textarea rows={3} maxLength={2000} value={v.bio} onChange={(e) => set('bio', e.target.value)} /></label>
      <div className="pp-field">
        <span>{t('Interests')}</span>
        <div className="pills">{Object.entries(CATEGORIES).map(([slug, c]) => {
          const on = v.interests.includes(slug)
          return <button key={slug} type="button" className={`pill-cat ${on ? 'on' : ''}`} style={{ '--c': c.color }} onClick={() => set('interests', on ? v.interests.filter((x) => x !== slug) : [...v.interests, slug])}><i />{categoryLabel(slug)}</button>
        })}</div>
      </div>
      <HangoutsField value={v.hangouts} onChange={(h) => set('hangouts', h)} features={features} />
      {error && <div className="pp-error">{t(error)}</div>}
      <div className="pp-actions">
        <button className="btn text small pp-logout" onClick={logout}>{t('Log out')}</button>
        <button className="btn text small" onClick={onDone}>{t('Cancel')}</button>
        <button className="btn small primary" disabled={saving || badAge || name.state === 'bad' || name.state === 'checking'} onClick={save}>{saving ? t('Saving…') : t('Save')}</button>
      </div>
    </motion.div>
  )
}

/** Profile picture: photos[0]. Uploads straight away; Save keeps it on the profile. */
function PhotoField({ user, onChange, onError }) {
  const { t } = useLang()
  const input = useRef(null)
  const [busy, setBusy] = useState(false)
  const pick = async (file) => {
    if (!file) return
    setBusy(true); onError(null)
    try { onChange([await uploadProfilePhoto(file), ...user.photos.slice(1)]) } catch (e) { onError(e.message) } finally { setBusy(false); input.current.value = '' }
  }
  return (
    <div className="pp-photo">
      <button type="button" className="pp-photo-av" onClick={() => input.current?.click()} aria-label={t('Change photo')} disabled={busy}>
        <Avatar user={user} size={84} />
        <span className="pp-photo-badge">{busy ? <span className="spin" /> : <Photo size={15} />}</span>
      </button>
      <div className="pp-photo-actions">
        <button type="button" className="btn small" onClick={() => input.current?.click()} disabled={busy}>{busy ? t('Uploading…') : t(user.photos.length ? 'Change photo' : 'Add a photo')}</button>
        {user.photos.length > 0 && <button type="button" className="btn text small" onClick={() => onChange(user.photos.slice(1))} disabled={busy}>{t('Remove photo')}</button>}
      </div>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => pick(e.target.files?.[0])} />
    </div>
  )
}

/** "You can find me at": up to 5 venues from the map, or anything typed. */
function HangoutsField({ value, onChange, features }) {
  const { t } = useLang()
  const [q, setQ] = useState('')
  const venues = useMemo(() => (features || []).filter((f) => f.properties.kind === 'place' && f.properties.title), [features])
  const term = q.trim().toLowerCase()
  const hits = term.length < 2 ? [] : venues.filter((f) => f.properties.title.toLowerCase().includes(term)).slice(0, 6)
  const add = (h) => { if (value.length < 5 && !value.some((x) => x.name.toLowerCase() === h.name.toLowerCase())) onChange([...value, h]); setQ('') }
  return (
    <div className="pp-field">
      <span>{t('You can find me at')}</span>
      <div className="pp-hangouts edit">
        <AnimatePresence initial={false}>
          {value.map((h) => (
            <motion.button layout key={h.name} type="button" className="pp-place on" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}
              onClick={() => onChange(value.filter((x) => x !== h))} title={t('Remove')}><Pin size={13} />{h.name}<X size={12} /></motion.button>
          ))}
        </AnimatePresence>
      </div>
      {value.length < 5 && (
        <label className="start-input"><Pin size={16} />
          <input value={q} placeholder={t('A place, e.g. Spatif')} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && q.trim()) { e.preventDefault(); add(hits[0] ? { name: hits[0].properties.title, place_id: hits[0].properties.event_id } : { name: q.trim(), place_id: null }) } }} />
        </label>
      )}
      {(hits.length > 0 || term.length >= 2) && (
        <div className="start-hits">
          {hits.map((f) => <button key={f.properties.event_id} type="button" className="start-hit" onClick={() => add({ name: f.properties.title, place_id: f.properties.event_id })}><span className="t">{f.properties.title}</span><span className="s">{f.properties.address || f.properties.district || ''}</span></button>)}
          {!hits.some((f) => f.properties.title.toLowerCase() === term) && <button type="button" className="start-hit" onClick={() => add({ name: q.trim(), place_id: null })}><span className="t">{t('Add “{name}”', { name: q.trim() })}</span></button>}
        </div>
      )}
    </div>
  )
}
