/**
 * Demo mode for presenting syrenka.me: double-click Home in the toolbar and a drawn cursor runs a
 * prerecorded, about five-minute tour of the app (demo/tour.js). Any real click, key press (Escape too),
 * touch or wheel stops it at once and leaves the app where it is, usable.
 *
 * The tour changes nothing for good: the interface settings, the language, the event search's switches and
 * everything else it touched in localStorage are snapshotted first and put back afterwards (the login
 * token is left alone, it may have been refreshed meanwhile).
 */
import './demo.css'
import { demoHost } from './host'
import { createDemo, Stopped } from './engine'
import { runTour } from './tour'
import { getMapFilter, restoreMapFilter } from '../data/mapFilter'

const SEED = 20261018 // same seed, same tour: the rehearsal looks like the presentation
const KEEP = new Set(['syrenka.token.v1'])
const STOP_ON = ['pointerdown', 'keydown', 'wheel', 'touchstart']

let running = null

function readStorage() {
  const out = {}
  try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (!KEEP.has(k)) out[k] = localStorage.getItem(k) } } catch { /* private mode */ }
  return out
}
function writeStorage(saved) {
  try {
    for (const k of Object.keys(readStorage())) if (!(k in saved)) localStorage.removeItem(k)
    for (const [k, v] of Object.entries(saved)) if (localStorage.getItem(k) !== v) localStorage.setItem(k, v)
  } catch { /* private mode */ }
}

function restore(snap) {
  const host = demoHost.current
  // a click away: the search panel and any popover close, so they reopen showing the restored state
  document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerType: 'mouse', isPrimary: true }))
  host?.closeCreate() // "+ Create event" left open: cancelled, nothing was sent
  host?.setMany(snap.values)
  if (host && host.lang !== snap.lang) host.setLang(snap.lang)
  restoreMapFilter(snap.filter)
  writeStorage(snap.storage)
  setTimeout(() => writeStorage(snap.storage), 800) // again once React's effects have written their own copies
}

/** Start the tour. `speed` > 1 rehearses faster (from the console in dev: syrenkaDemo.start({ speed: 4 })). */
export function startDemo({ speed = 1, seed = SEED } = {}) {
  const host = demoHost.current
  if (running || !host) return
  const snap = { values: host.values, lang: host.lang, filter: getMapFilter(), storage: readStorage() }
  const root = document.documentElement
  const demo = createDemo({ seed, speed, getMap: () => demoHost.current?.getMap() })
  const self = { demo, scene: null, startedAt: Date.now(), log: null }
  const onInput = (e) => { if (e.isTrusted) stop('input') }
  function stop(why) {
    if (running !== self) return
    running = null
    for (const t of STOP_ON) window.removeEventListener(t, onInput, true)
    demo.stop()
    root.classList.remove('demo-running')
    delete root.dataset.demoScene
    restore(snap)
    last = { why, scene: self.scene, seconds: Math.round((Date.now() - self.startedAt) / 1000), log: self.log, missed: demo.missed }
  }
  self.stop = stop
  running = self
  root.classList.add('demo-running')
  for (const t of STOP_ON) window.addEventListener(t, onInput, { capture: true, passive: true })
  runTour(demo, { onScene: (name) => { self.scene = name; root.dataset.demoScene = name } })
    .then((log) => { self.log = log; stop('done') })
    .catch((e) => { if (!(e instanceof Stopped)) console.error('[demo]', e); stop(e instanceof Stopped ? 'input' : 'error') }) // eslint-disable-line no-console
}

export const stopDemo = () => running?.stop('stopped')

let last = null
/** Where the tour is (or how the last one ended): handy for rehearsing. */
export const demoStatus = () => (running ? { running: true, scene: running.scene, seconds: Math.round((Date.now() - running.startedAt) / 1000) } : { running: false, last })

if (import.meta.env.DEV) window.syrenkaDemo = { start: startDemo, stop: stopDemo, status: demoStatus }
