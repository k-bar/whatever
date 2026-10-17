import { useEffect, useReducer, useRef, useState } from 'react'
import { useConfig } from '../config/store'
import { categoryColor } from '../data/categories'

/**
 * Start page decoration: "people in Warsaw are doing stuff together". Made-up people and plans (not data,
 * on purpose) pop in and out over the washed-out map, and dotted lines travel from one person to another
 * in ~1.5 s, as if they were connecting. Purely visual: it fades away with the start page when the map
 * is entered, so the real map never shows any of it.
 */

// Invented spots: [lng, lat, plan, face] — face is an initial, or null for a person figure
const SPOTS = [
  [20.985, 52.268, 'film', 'O'], [20.94, 52.29, 'run', null], [20.96, 52.235, 'club', 'K'], [21.02, 52.195, 'picnic', null],
  [21.04, 52.255, 'concert', 'M'], [21.08, 52.24, 'games', null], [21.04, 52.15, 'yoga', 'Z'], [21.09, 52.165, 'exhibition', null],
  [20.975, 52.215, 'study', 'T'], [21.06, 52.232, 'picnic', 'A'], [20.9, 52.25, 'sport', null], [21.05, 52.285, 'party', 'J'],
  [20.98, 52.32, 'run', 'P'], [21.03, 52.24, 'meetup', null], [21.012, 52.222, 'theatre', 'E'], [20.995, 52.248, 'film', null],
  [21.06, 52.13, 'run', 'W'], [21.0, 52.212, 'picnic', null], [21.15, 52.21, 'picnic', 'N'], [21.1, 52.225, 'concert', null],
  [20.93, 52.2, 'games', 'B'], [21.13, 52.27, 'sport', null],
  // around the edges, where the headline and search don't cover the map
  [20.9, 52.31, 'picnic', 'L'], [20.87, 52.27, 'run', null], [21.03, 52.33, 'concert', 'S'], [21.1, 52.31, 'film', null],
  [21.18, 52.29, 'meetup', 'R'], [21.2, 52.24, 'party', null], [21.19, 52.18, 'yoga', 'D'], [21.12, 52.14, 'picnic', null],
  [20.97, 52.14, 'study', 'C'], [20.9, 52.16, 'sport', null], [20.86, 52.21, 'exhibition', 'H'], [21.0, 52.11, 'games', null],
  [20.88, 52.3, 'theatre', null], [21.23, 52.2, 'run', 'G'],
]
const PLANS = { // plan -> [category (colour), emoji]
  film: ['film', '🎬'], run: ['running', '🏃'], picnic: ['meetups', '🌳'], club: ['nightlife', '🪩'], concert: ['music', '🎸'],
  yoga: ['yoga', '🧘'], games: ['meetups', '🎲'], exhibition: ['exhibitions', '🖼️'], study: ['study_buddies', '📚'],
  sport: ['sports', '⚽'], party: ['festivals', '🎉'], meetup: ['meetups', '🤝'], theatre: ['theatre', '🎭'],
}

const POP_MS = 380
const SWAP_MS = 2200 // one person pops out, another pops in
const LINK_EVERY_MS = 1700 // a new line starts
const DRAW_MS = 1500 // a line travels from one person to the other
const HOLD_MS = 900 // then stays a moment before fading
const FADE_MS = 600

const Person = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7.6" r="4.3" /><path d="M3.4 22c0-5 3.9-8.4 8.6-8.4s8.6 3.4 8.6 8.4z" /></svg>

/** Spots that land on screen without covering the headline, search, chips or header. */
function placeSpots(map, layer) {
  const box = layer.getBoundingClientRect()
  const keepClear = [...layer.parentElement.querySelectorAll('.landing-head, .hero-center > *, .hero-more')]
    .map((el) => el.getBoundingClientRect()).filter((r) => r.width && r.height)
  const out = []
  SPOTS.forEach((s, i) => {
    const pt = map.project([s[0], s[1]])
    const x = pt.x - box.left, y = pt.y - box.top
    const r = { left: pt.x - 30, right: pt.x + 90, top: pt.y - 64, bottom: pt.y + 10 } // pin + tile, with room
    if (x < 30 || y < 70 || x > box.width - 100 || y > box.height - 20) return
    if (keepClear.some((k) => r.left < k.right && r.right > k.left && r.top < k.bottom && r.bottom > k.top)) return
    out.push({ i, x, y })
  })
  return out
}

export function LandingNetwork({ getMap, mobile }) {
  const { values } = useConfig()
  const layer = useRef(null)
  const [spots, setSpots] = useState([])
  const s = useRef({ shown: [], links: [], pings: {} }) // mutable scene; render() redraws it
  const [, render] = useReducer((n) => n + 1, 0)

  // where the made-up people stand: projected onto the real map behind the wash
  useEffect(() => {
    let map, timer
    const place = () => { if (map && layer.current) setSpots(placeSpots(map, layer.current)) }
    const wait = () => {
      map = getMap()
      // only the camera is needed to place people, not the tiles: start before the map has finished loading
      if (!map || !map.getContainer().clientWidth) { timer = setTimeout(wait, 250); return }
      place()
      map.on('moveend', place)
    }
    wait()
    window.addEventListener('resize', place)
    return () => { clearTimeout(timer); map?.off('moveend', place); window.removeEventListener('resize', place) }
  }, [getMap])

  // the scene: people popping in and out, lines travelling between them
  useEffect(() => {
    if (!spots.length) return
    const timers = []
    const later = (fn, ms) => timers.push(setTimeout(fn, ms))
    const scene = s.current
    const max = Math.min(spots.length, mobile ? 6 : 10)
    let uid = 0
    scene.shown = []
    scene.links = []

    const live = () => scene.shown.filter((b) => !b.out)
    const show = () => {
      const taken = new Set(scene.shown.map((b) => b.spot.i))
      const free = spots.filter((p) => !taken.has(p.i))
      if (!free.length) return
      scene.shown.push({ key: ++uid, spot: free[Math.floor(Math.random() * free.length)], out: false })
      render()
    }
    const hide = (b) => {
      b.out = true
      render()
      later(() => { scene.shown = scene.shown.filter((x) => x !== b); render() }, POP_MS)
    }
    const link = () => {
      const people = live()
      if (people.length < 2) return
      const a = people[Math.floor(Math.random() * people.length)]
      const others = people.filter((b) => b !== a)
      const b = others[Math.floor(Math.random() * others.length)]
      const l = { key: ++uid, a: a.spot, b: b.spot, fading: false }
      scene.links.push(l)
      render()
      later(() => { scene.pings[b.spot.i] = (scene.pings[b.spot.i] || 0) + 1; render() }, DRAW_MS) // arrives: ping
      later(() => { l.fading = true; render() }, DRAW_MS + HOLD_MS)
      later(() => { scene.links = scene.links.filter((x) => x !== l); render() }, DRAW_MS + HOLD_MS + FADE_MS)
    }

    for (let n = 0; n < max; n++) later(show, 200 + n * 220) // pop in one after another
    const swap = setInterval(() => {
      const people = live()
      if (people.length >= max && spots.length > max) { hide(people[0]); later(show, POP_MS / 2) } else if (people.length < max) show()
    }, SWAP_MS)
    const lines = values.reduceMotion ? null : setInterval(link, LINK_EVERY_MS)
    later(link, 200 + max * 220)
    return () => { timers.forEach(clearTimeout); clearInterval(swap); if (lines) clearInterval(lines) }
  }, [spots, mobile, values.reduceMotion])

  const { shown, links, pings } = s.current
  return (
    <div className="ln-layer" ref={layer} aria-hidden="true">
      <svg className="ln-links">
        {links.map((l) => {
          const ax = l.a.x, ay = l.a.y - 32, bx = l.b.x, by = l.b.y - 32 // from face to face
          const lift = Math.min(160, Math.hypot(bx - ax, by - ay) * 0.3) // arc gently upwards
          const d = `M${ax},${ay} Q${(ax + bx) / 2},${Math.min(ay, by) - lift} ${bx},${by}`
          const color = categoryColor(PLANS[SPOTS[l.a.i][2]][0])
          return (
            <g key={l.key} className={`ln-link ${l.fading ? 'fading' : ''}`} style={{ '--c': color }}>
              <mask id={`ln-m${l.key}`} maskUnits="userSpaceOnUse"><path d={d} className="ln-reveal" pathLength="1" /></mask>
              <path d={d} className="ln-dots" mask={`url(#ln-m${l.key})`} />
              <circle r="4.5" className="ln-head"><animateMotion dur={`${DRAW_MS}ms`} fill="freeze" path={d} keyTimes="0;1" keySplines="0.4 0 0.2 1" calcMode="spline" /></circle>
            </g>
          )
        })}
      </svg>
      {shown.map((b) => {
        const [, , plan, face] = SPOTS[b.spot.i]
        const [category, emoji] = PLANS[plan]
        return (
          <div key={b.key} className="ln-bubble" style={{ left: b.spot.x - 20, top: b.spot.y - 52, '--c': categoryColor(category) }}>
            <span className={`lb ${b.out ? 'out' : ''}`}>
              <span className="lb-pin">
                <svg className="lb-shape" viewBox="0 0 40 52"><path d="M20 50.5S4 32.2 4 20a16 16 0 1 1 32 0c0 12.2-16 30.5-16 30.5z" /></svg>
                <span className={`lb-face ${face ? 'initial' : ''}`}>{face || <Person />}</span>
              </span>
              <span className="lb-tile"><span className="lb-person"><Person /></span><span className="lb-emoji">{emoji}</span></span>
            </span>
            {pings[b.spot.i] > 0 && <span key={pings[b.spot.i]} className="ln-ping" />}
          </div>
        )
      })}
    </div>
  )
}
