import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { fetchSources } from '../data/api'
import { categoryColor, categoryLabel } from '../data/categories'
import { CloseButton } from './CloseButton'
import { Star } from './Icons'
import { StartPointPicker } from './StartPointPicker'

const AV = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']

function Shell({ title, onClose, children, sub }) {
  const spring = useSpring()
  return (
    <motion.aside className="side-panel surface" initial={{ x: -40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -40, opacity: 0 }} transition={spring}>
      <div className="sp-head">
        <div><h2>{title}</h2>{sub && <div className="mb-sub">{sub}</div>}</div>
        <CloseButton size={34} onClick={onClose} />
      </div>
      <div className="sp-scroll">{children}</div>
    </motion.aside>
  )
}

export function ProfilePanel({ onClose }) {
  return (
    <Shell title="Your profile" sub="What others see when you ask to join" onClose={onClose}>
      <div className="profile-hero">
        <div className="big">P</div>
        <h2 style={{ fontSize: 22 }}>Philip</h2>
        <div className="mb-sub">New in Warsaw · Mokotów · speaks EN / PL</div>
        <div className="chips">{['music', 'running', 'theatre', 'meetups'].map((c) => <span className="badge" key={c} style={{ background: `color-mix(in srgb, ${categoryColor(c)} 15%, transparent)`, color: categoryColor(c) }}>{categoryLabel(c)}</span>)}</div>
        <p className="mb-text" style={{ marginTop: 12 }}>Looking for people to go to concerts with and a squad for Sunday runs along the Vistula.</p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12 }}>
          <button className="btn small">Instagram</button><button className="btn small">GitHub</button><button className="btn small primary">Edit profile</button>
        </div>
      </div>
      <div className="blk-title" style={{ padding: '0 10px' }}>Join requests</div>
      {[['Ola', 'wants to join your picnic', 'accept'], ['Kamil', 'wants to join your run', 'accept']].map(([n, t], i) => (
        <div className="sp-row" key={i}><span className="av" style={{ background: AV[i] }}>{n[0]}</span><span><div className="t">{n}</div><div className="s">{t}</div></span>
          <span className="right" style={{ display: 'flex', gap: 6 }}><button className="btn small primary">Accept</button><button className="btn small">Pass</button></span></div>
      ))}
      <div className="blk-title" style={{ padding: '0 10px', marginTop: 18 }}>Set my location to</div>
      <StartPointPicker />
    </Shell>
  )
}

export function MessagesPanel({ onClose }) {
  const msgs = [['Ola', 'See you at the boulevards at 18?', '2m'], ['Squad: Jazz Jamboree', 'Marta: I got the tickets 🎷', '1h'], ['Kamil', 'Pace 5:30 ok for you?', '3h'], ['Tomek', 'Board games Friday, bring snacks', 'yday']]
  return (
    <Shell title="Messages" sub="Only people you met at an event" onClose={onClose}>
      {msgs.map(([n, t, when], i) => (
        <div className="sp-row" key={i}><span className="av" style={{ background: AV[i % AV.length] }}>{n[0]}</span><span><div className="t">{n}</div><div className="s">{t}</div></span><span className="right">{when}</span></div>
      ))}
    </Shell>
  )
}

export function FavouritesPanel({ onClose, features, favourites, onPick }) {
  const list = features.filter((f) => favourites.has(f.properties.event_id))
  return (
    <Shell title="Favourite spots" sub={`${list.length} starred · shown on the map by default`} onClose={onClose}>
      {list.map((f) => {
        const p = f.properties
        return (
          <button className="sp-row" key={f.id} onClick={() => onPick(f)} style={{ width: '100%', textAlign: 'left' }}>
            <span className="av" style={{ background: categoryColor(p.categories?.[0]) }}><Star size={18} filled /></span>
            <span><div className="t">{p.title}</div><div className="s">{p.venue_name || p.address || p.district || ''}</div></span>
          </button>
        )
      })}
      {!list.length && <div className="res-empty">Star places from their map box and they appear here.</div>}
    </Shell>
  )
}

export function SourcesPanel({ onClose }) {
  const [sources, setSources] = useState([])
  useEffect(() => { fetchSources().then(setSources) }, [])
  const max = Math.max(1, ...sources.map((s) => s.item_count))
  return (
    <Shell title="APIs I'm plugged in to" sub="Where every pin comes from" onClose={onClose}>
      {sources.map((s) => (
        <div className="sp-row" key={s.slug} style={{ display: 'block' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="t">{s.name}</span>
            <span className={`badge ${s.is_reliable ? 'accent' : ''}`} style={{ marginLeft: 'auto' }}>{s.is_reliable ? 'reliable' : s.last_status || 'community'}</span>
          </div>
          <div className="s">{s.item_count.toLocaleString()} items{s.last_run_at ? ` · last run ${new Date(s.last_run_at).toLocaleString('en-GB', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}` : ''}</div>
          <div className="src-bar"><i style={{ width: `${(s.item_count / max) * 100}%`, background: s.is_reliable ? 'var(--accent)' : 'var(--fg-3)' }} /></div>
        </div>
      ))}
    </Shell>
  )
}
