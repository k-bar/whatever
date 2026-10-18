import { useEffect, useState } from 'react'
import { categoryColor, categoryLabel } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { getLang, locale, useLang } from '../i18n'
import { Clock, MapIcon, Pin, Users } from './Icons'

/**
 * "Everything we know" in an expanded map box: the full event from GET /events/{id} (description, every
 * date, place, opening hours, who it's for, contact, spots, host, source), laid out as readable sections
 * instead of raw data. Until the API answers, or for pins it doesn't know (private user events, walking
 * routes), it uses what the pin already carries.
 */
const BASE = import.meta.env.VITE_API_URL || '/api'
const cache = new Map()
function fetchEventDetails(id) {
  if (!/^\d+$/.test(String(id))) return Promise.resolve(null)
  const key = `${id}:${getLang()}`
  if (!cache.has(key)) {
    cache.set(key, fetch(`${BASE}/events/${id}?lang=${getLang()}`, { signal: AbortSignal.timeout(8000) })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null))
  }
  return cache.get(key)
}

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const dayName = (i) => { const s = new Date(2024, 0, 1 + i).toLocaleDateString(locale(), { weekday: 'long' }); return s[0].toUpperCase() + s.slice(1) } // 1 Jan 2024 was a Monday
const time = (iso) => new Date(iso).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
const longDate = (iso) => new Date(iso).toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: 'numeric' })
const SOURCES = {
  warsaw_events: 'City of Warsaw', warsaw_open_data: 'City of Warsaw', warsaw_pitches: 'City of Warsaw: open pitches',
  warsaw_toilets: 'City of Warsaw: public toilets', warsaw_aed: 'City of Warsaw: defibrillators', kupbilecik: 'KupBilecik',
  'syrenka-users': 'Syrenka users', user: 'Syrenka users', osm: 'OpenStreetMap',
}

function contactLink(key, value) {
  const v = String(value).trim()
  if (/^https?:\/\//i.test(v)) return { href: v, text: v.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '') }
  if (/@/.test(v) && !/\s/.test(v)) return { href: `mailto:${v}`, text: v }
  if (/^[+\d][\d\s()-]{6,}$/.test(v)) return { href: `tel:${v.replace(/[^\d+]/g, '')}`, text: v }
  return { href: null, text: v }
}

/** One date line: "Sat 18 Oct · 19:00 – 21:00", or "Every day, until 31 December 2027". */
function DateLine({ occ, t }) {
  const end = occ.ends_at && new Date(occ.ends_at)
  if (occ.daily || (end && end - new Date(occ.starts_at) > 3 * 864e5)) {
    return <li>{t(occ.daily ? 'Every day' : 'Ongoing')}{end ? `, ${t('until {date}', { date: longDate(occ.ends_at) })}` : ''}</li>
  }
  const sameDay = end && end.toDateString() === new Date(occ.starts_at).toDateString()
  return <li>{fmtWhen(occ.starts_at)}{sameDay && end - new Date(occ.starts_at) > 0 ? ` – ${time(occ.ends_at)}` : ''}</li>
}

export function EventDetails({ feature }) {
  const { t } = useLang()
  const p = feature.properties
  const [api, setApi] = useState(null)
  useEffect(() => {
    let on = true
    setApi(null)
    fetchEventDetails(p.event_id).then((d) => { if (on) setApi(d) })
    return () => { on = false }
  }, [p.event_id])

  const e = { ...p, ...(api || {}) }
  const about = (e.text_plain || '').trim()
  const showAbout = about && about !== (p.lead || '').trim()
  const now = Date.now()
  const occs = (api?.occurrences || (p.starts_at ? [{ starts_at: p.starts_at, ends_at: p.ends_at, daily: p.daily }] : []))
    .filter((o) => new Date(o.ends_at || o.starts_at).getTime() >= now - 3 * 3600e3)
  const hours = e.opening_hours && typeof e.opening_hours === 'object' ? e.opening_hours : null
  const today = (new Date().getDay() + 6) % 7
  const contact = Object.entries(e.contact || {}).filter(([, v]) => v)
  for (const k of ['phone', 'website', 'email']) if (p[k] && !contact.some(([, v]) => v === p[k])) contact.push([k, p[k]])
  const audience = (e.audience || []).filter(Boolean)
  const cats = (e.categories || []).filter((c) => c !== 'other')
  const host = e.host?.display_name
  const source = SOURCES[e.source] || e.source
  const where = [e.venue_name, e.address, e.district].filter(Boolean)
  const lat = e.lat ?? feature.geometry?.coordinates?.[1], lng = e.lng ?? feature.geometry?.coordinates?.[0]

  return (
    <div className="blk ev-details">
      <div className="blk-title">{t('Everything we know')}</div>

      {showAbout && (
        <section className="evd-sec">
          <h4>{t('About')}</h4>
          {about.split(/\n{2,}|\n(?=\S)/).map((para, i) => <p key={i}>{para.trim()}</p>)}
        </section>
      )}

      {occs.length > 0 && (
        <section className="evd-sec">
          <h4><Clock size={14} />{t(occs.length > 1 ? 'Dates' : 'When')}</h4>
          <ul className="evd-dates">{occs.slice(0, 6).map((o, i) => <DateLine key={o.id || i} occ={o} t={t} />)}</ul>
          {occs.length > 6 && <div className="evd-more">{t('and {n} more dates', { n: occs.length - 6 })}</div>}
        </section>
      )}

      {where.length > 0 && (
        <section className="evd-sec">
          <h4><Pin size={14} />{t('Where')}</h4>
          {e.venue_name && <div className="evd-strong">{e.venue_name}</div>}
          {e.address && <div>{e.address}</div>}
          {e.district && <div className="evd-muted">{e.district}</div>}
          {Number.isFinite(lat) && Number.isFinite(lng) && (
            <a className="evd-link" href={`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`} target="_blank" rel="noreferrer">{t('Directions ↗')}</a>
          )}
        </section>
      )}

      {hours && (
        <section className="evd-sec">
          <h4><Clock size={14} />{t('Opening hours')}</h4>
          <table className="evd-hours"><tbody>
            {DAYS.map((d, i) => (
              <tr key={d} className={i === today ? 'today' : ''}>
                <th>{dayName(i)}</th>
                <td>{hours[d] ? (/^0?0:00-24:00$/.test(hours[d]) ? t('Open 24 hours') : hours[d].replace('-', ' – ')) : t('Closed')}</td>
              </tr>
            ))}
          </tbody></table>
        </section>
      )}

      {(audience.length > 0 || cats.length > 0) && (
        <section className="evd-sec">
          <h4><Users size={14} />{t('For whom')}</h4>
          <div className="evd-chips">
            {cats.map((c) => <span key={c} className="badge" style={{ background: `color-mix(in srgb, ${categoryColor(c)} 14%, transparent)`, color: categoryColor(c) }}>{categoryLabel(c)}</span>)}
            {audience.map((a) => <span key={a} className="badge">{a}</span>)}
          </div>
        </section>
      )}

      {(e.capacity || host) && (
        <section className="evd-sec">
          <h4><Users size={14} />{t('Hosting')}</h4>
          {host && <div>{t('Hosted by {name}', { name: host })}</div>}
          {e.capacity && <div className="evd-muted">{e.seats_left != null ? t('{n} of {total} spots left', { n: e.seats_left, total: e.capacity }) : t('{total} spots', { total: e.capacity })}</div>}
        </section>
      )}

      {contact.length > 0 && (
        <section className="evd-sec">
          <h4>{t('Contact')}</h4>
          {contact.map(([k, v]) => { const l = contactLink(k, v); return <div key={k}>{l.href ? <a className="evd-link" href={l.href} target={l.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer">{l.text}</a> : l.text}</div> })}
        </section>
      )}

      {source && (
        <section className="evd-sec evd-source">
          <MapIcon size={13} /><span>{t('Source: {name}', { name: t(source) })}</span>
        </section>
      )}
    </div>
  )
}
