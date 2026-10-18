import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { createUserEvent } from '../data/api'
import { AUDIENCES } from '../data/categories'
import { SEARCH_TYPES, TYPES, typeColor, typeLabel } from '../data/types'
import { CloseButton } from './CloseButton'
import { Check, Globe, Lock, Photo, Pin, UserCheck, Users } from './Icons'
import { LoginForm } from './LoginForm'
import { VerifyBanner } from './Account'
import { useLoggedIn, useMe } from '../data/me'
import { DateField } from './Calendar'
import { getLang, useLang } from '../i18n'

const AUDIENCE_ICON = { public: Globe, public_confirm: UserCheck, friends: Users, invite: Lock }
const pad = (n) => String(n).padStart(2, '0')
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

/** Next full hour, so the form opens on something sensible ("today, 19:00"). */
function defaults() {
  const d = new Date()
  d.setHours(d.getHours() + 1, 0, 0, 0)
  return { date: ymd(d), start: `${pad(d.getHours())}:00` }
}

/** Date + start/end time (local) -> ISO. An end time before the start means it runs past midnight. */
function toTimes(date, start, end) {
  const s = new Date(`${date}T${start}`)
  if (!end) return { starts_at: s.toISOString(), ends_at: null }
  const e = new Date(`${date}T${end}`)
  if (e <= s) e.setDate(e.getDate() + 1)
  return { starts_at: s.toISOString(), ends_at: e.toISOString() }
}

/** Street + number near the pin (OpenStreetMap Nominatim), shown under the place field. */
const addrCache = new Map() // the pin is dragged in small steps; ~10 m cells avoid re-asking Nominatim
async function reverseGeocode([lng, lat], signal) {
  const key = `${lng.toFixed(4)},${lat.toFixed(4)},${getLang()}`
  if (addrCache.has(key)) return addrCache.get(key)
  const out = await reverseGeocodeNow([lng, lat], signal)
  addrCache.set(key, out)
  return out
}
async function reverseGeocodeNow([lng, lat], signal) {
  const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=${lat}&lon=${lng}&accept-language=${getLang()}`
  const j = await (await fetch(url, { signal })).json()
  const a = j.address || {}
  const street = [a.road || a.pedestrian || a.square || a.park, a.house_number].filter(Boolean).join(' ')
  return [street, a.suburb || a.city_district].filter(Boolean).join(', ') || j.display_name || null
}

/**
 * "+ Create event": full-height panel on the right. The red draggable pin on the map is where it happens.
 * Done -> POST /userevents (backend/app/userevents) -> onCreated(feature) drops it onto the map.
 * Creating needs an account: logged out, the panel shows "Log in" first (what was typed is kept).
 */
export function CreateEventPanel({ pin, onClose, onCreated }) {
  const spring = useSpring()
  const { t } = useLang()
  const [form, setForm] = useState(() => ({ title: '', subtitle: '', description: '', type: null, audience: 'public', venue: '', end: '', ...defaults() }))
  const [photo, setPhoto] = useState(null) // File
  const [address, setAddress] = useState(null)
  const [saving, setSaving] = useState(false)
  const me = useMe() // creating needs a confirmed email: the banner says so up front
  const [error, setError] = useState(null)
  const loggedIn = useLoggedIn() // a session that expired mid-way (LoginRequired) flips it back to "Log in"
  const retry = useRef(false) // Done was pressed while logged out: create right after logging in
  const fileRef = useRef(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target ? e.target.value : e }))

  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  useEffect(() => {
    if (!pin) return
    const ctl = new AbortController()
    const timer = setTimeout(() => reverseGeocode(pin, ctl.signal).then(setAddress).catch(() => {}), 450)
    return () => { clearTimeout(timer); ctl.abort() }
  }, [pin])

  const missing = [form.title.trim().length < 3 && 'a name', !form.type && 'an event type', !form.date && 'a date', !form.start && 'a start time', !pin && 'a place'].filter(Boolean)
  const valid = missing.length === 0

  const submit = async () => {
    if (!valid || saving) return
    setSaving(true); setError(null)
    try {
      const { feature, event } = await createUserEvent({
        title: form.title.trim(),
        subtitle: form.subtitle.trim() || null,
        description: form.description.trim() || null,
        event_type: form.type,
        audience: form.audience,
        ...toTimes(form.date, form.start, form.end),
        lng: pin[0], lat: pin[1],
        venue_name: form.venue.trim() || null,
        address,
      }, photo)
      onCreated(feature, event)
    } catch (e) {
      setSaving(false)
      if (e.loginRequired) { retry.current = true; return } // session expired: back to "Log in"
      setError(e.status ? t(e.message) : t('Could not reach the server. Try again in a moment.'))
    }
  }
  const afterLogin = () => { if (retry.current) { retry.current = false; submit() } }

  return (
    <motion.aside className="create-panel surface" initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={spring}
      aria-label={t('Create event')}>
      <div className="sp-head">
        <div><h2>{t(loggedIn ? 'Create event' : 'Log in')}</h2><div className="mb-sub">{t(loggedIn ? 'It goes on the map as soon as you tap Done' : 'You need an account to create events')}</div></div>
        <CloseButton size={34} onClick={onClose} />
      </div>

      {!loggedIn ? (
        <div className="sp-scroll ce-scroll"><LoginForm onDone={afterLogin} intro={t('Log in so people know who is hosting. Your event stays filled in.')} /></div>
      ) : (<>
      <div className="sp-scroll ce-scroll">
        <VerifyBanner me={me} />
        <label className="ce-field">
          <span className="ce-label">{t('Event name')}</span>
          <input className="ce-input" value={form.title} onChange={set('title')} maxLength={200} placeholder={t('Sunday run along the Vistula')} autoFocus />
        </label>
        <label className="ce-field">
          <span className="ce-label">{t('Subtitle')}</span>
          <input className="ce-input" value={form.subtitle} onChange={set('subtitle')} maxLength={200} placeholder={t('Easy 5k, all paces welcome')} />
        </label>
        <label className="ce-field">
          <span className="ce-label">{t('Description')}</span>
          <textarea className="ce-input" rows={4} value={form.description} onChange={set('description')} maxLength={5000} placeholder={t('What happens, what to bring, how to find you…')} />
        </label>

        <div className="ce-field">
          <span className="ce-label">{t('Event type')}</span>
          <div className="ce-types">
            {/* any type at all (data/types.js): the invite's pin gets exactly this type */}
            {SEARCH_TYPES.map((id) => (
              <button key={id} type="button" className={`pill-cat ${form.type === id ? 'on' : ''}`} style={{ '--c': typeColor(id) }} onClick={() => set('type')(id)} aria-pressed={form.type === id}>
                <span aria-hidden="true">{TYPES[id].emoji}</span>{typeLabel(id)}
              </button>
            ))}
          </div>
        </div>

        <div className="ce-field">
          <span className="ce-label">{t('Date')}</span>
          <div className="ce-row">
            <DateField value={form.date} onChange={set('date')} label={t('Date')} />
            <input className="ce-input ce-time" type="time" value={form.start} onChange={set('start')} aria-label={t('Starts')} />
            <span className="ce-dash">–</span>
            <input className="ce-input ce-time" type="time" value={form.end} onChange={set('end')} aria-label={t('Ends (optional)')} />
          </div>
        </div>

        <div className="ce-field">
          <span className="ce-label">{t('Place')}</span>
          <input className="ce-input" value={form.venue} onChange={set('venue')} maxLength={200} placeholder={t('Venue or meeting point (optional)')} />
          <div className="ce-where"><Pin size={15} /><span>{address || t('Pinned on the map')}<small>{t('Drag the red pin or tap the map to move it')}</small></span></div>
        </div>

        <div className="ce-field">
          <span className="ce-label">{t('Audience')}</span>
          <div className="ce-audience" role="radiogroup">
            {Object.entries(AUDIENCES).map(([slug, a]) => {
              const Icon = AUDIENCE_ICON[slug]
              const on = form.audience === slug
              return (
                <button key={slug} type="button" role="radio" aria-checked={on} className={`ce-aud ${on ? 'on' : ''}`} onClick={() => set('audience')(slug)}>
                  <span className="ic"><Icon size={18} /></span>
                  <span className="txt"><b>{t(a.label)}</b><small>{t(a.hint)}</small></span>
                  <span className="tick">{on && <Check size={14} stroke={3} />}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="ce-field">
          <span className="ce-label">{t('Photo')}</span>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { setPhoto(e.target.files?.[0] || null); e.target.value = '' }} />
          {preview ? (
            <div className="ce-photo has" style={{ backgroundImage: `url(${preview})` }}>
              <button type="button" className="btn small" onClick={() => fileRef.current?.click()}>{t('Change')}</button>
              <button type="button" className="btn small" onClick={() => setPhoto(null)}>{t('Remove')}</button>
            </div>
          ) : (
            <button type="button" className="ce-photo" onClick={() => fileRef.current?.click()}><Photo size={22} />{t('Add photo')}</button>
          )}
        </div>
      </div>

      <div className="ce-foot">
        {error && <div className="ce-error" role="alert">{error}</div>}
        {!valid && !error && <div className="ce-hint">{t('Still needed')}: {missing.map((m) => t(m)).join(', ')}</div>}
        <button type="button" className="btn primary ce-done" disabled={!valid || saving} onClick={submit}>
          {saving ? t('Creating…') : t('Done')}
        </button>
      </div>
      </>)}
    </motion.aside>
  )
}
