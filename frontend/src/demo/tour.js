/**
 * The presentation tour: about five minutes through the whole app, scene by scene, with the drawn cursor
 * (demo/engine.js). Every scene finds its elements by stable selectors and simply skips what isn't there
 * (logged out, no people sharing, a layer switched off…), so the tour never gets stuck.
 *
 * Nothing here writes to the server: "I'm going" / "Ask to join" is only pretended (fakeClick), Create
 * event is cancelled, chats are never opened (that would mark them read), Share my area isn't touched.
 * The settings it changes are put back by demo/index.js.
 */
import { getLang } from '../i18n'
import { typeLabel } from '../data/types'
import { Stopped } from './engine'
import { demoHost } from './host'

const TARGET_MS = 5 * 60 * 1000
const CENTRUM = [21.0106, 52.2302] // Śródmieście, around the Centrum metro station
const SEARCH = '.top-left .search input'
const PIN_BTN = '.pinmenu:not(.peoplemenu) > .pin-btn'
const PIN_OPT = (id) => `.pin-menu [data-opt="${id}"]`

const isPhone = () => innerWidth < 768
// the app's own view, not the DOM: the start page stays in the DOM while it fades out
const view = () => demoHost.current?.view
const settled = () => !document.querySelector('.app.flying, .search-ghost')

/** Elements matching `sel` that are fully on screen. */
const onScreen = (sel, root = document) => [...root.querySelectorAll(sel)].filter((el) => {
  const b = el.getBoundingClientRect()
  return b.width > 4 && b.height > 4 && b.top >= 8 && b.left >= 0 && b.bottom <= innerHeight - 8 && b.right <= innerWidth
})
/** The element that scrolls `el` (its nearest scrollable ancestor). */
function scrollerOf(el) {
  for (let n = el?.parentElement; n; n = n.parentElement) {
    const o = getComputedStyle(n).overflowY
    if ((o === 'auto' || o === 'scroll') && n.scrollHeight > n.clientHeight + 4) return n
  }
  return null
}

export async function runTour(d, { onScene } = {}) {
  const t0 = performance.now()
  const elapsed = () => (performance.now() - t0) * d.speed
  const log = []

  async function scene(name, fn) {
    d.check()
    onScene?.(name)
    const s = performance.now()
    try { await fn() } catch (e) {
      if (e instanceof Stopped) throw e
      console.warn(`[demo] "${name}" skipped:`, e) // eslint-disable-line no-console
    }
    log.push([name, Math.round((performance.now() - s) * d.speed / 100) / 10])
    await d.sleep(d.r(350, 800))
  }

  // ---------- small helpers shared by the scenes ----------
  const pause = (a = 500, b = 1100) => d.sleep(d.r(a, b))
  const onMap = async () => {
    if (view() !== 'map' && !(await d.click('.hero-search .hero-go'))) await d.click('.landing-nav > button')
    return !!(await d.waitFor(() => view() === 'map' && settled() && d.$('.toolbar'), 8000))
  }
  /** Click a bit of map with nothing on it (closes the search panel and popovers like a real click away). */
  async function clickEmptyMap() {
    const m = d.map()
    if (!m) return false
    const canvas = m.getCanvas(), b = canvas.getBoundingClientRect()
    const layers = ['wl-dots', 'wl-icons', 'wl-amenities', 'wl-walks-hit'].filter((l) => m.getLayer(l))
    for (let i = 0; i < 12; i++) {
      const p = d.mapSpot()
      if (document.elementFromPoint(p.x, p.y) !== canvas) continue
      const x = p.x - b.left, y = p.y - b.top
      if (m.queryRenderedFeatures([[x - 16, y - 16], [x + 16, y + 16]], { layers }).length) continue
      await d.moveTo(p.x, p.y)
      return d.clickMap()
    }
    return false
  }
  /** Open the pin box, run fn, close it again with the same button. */
  async function inPinBox(fn) {
    if (!(await d.click(PIN_BTN))) return
    if (!(await d.waitFor('.pin-menu', 2000))) return
    await pause(500, 900)
    await fn()
    if (document.querySelector('.pin-menu')) await d.click(PIN_BTN)
  }
  const toggle = async (sel, wait = [700, 1300]) => { if (await d.click(sel)) await pause(...wait) }
  /** Drag the map in a few hand-sized pulls until `lngLat` sits near a free spot. */
  async function dragToward(lngLat, pulls = 3) {
    const m = d.map()
    if (!m) return
    for (let i = 0; i < pulls; i++) {
      const b = m.getCanvas().getBoundingClientRect()
      const p = m.project(lngLat), want = d.mapSpot()
      const dx = want.x - (p.x + b.left), dy = want.y - (p.y + b.top)
      if (Math.hypot(dx, dy) < 60) return
      const k = Math.min(1, 380 / Math.hypot(dx, dy))
      const start = { x: Math.min(innerWidth - 60, Math.max(60, want.x - dx * k)), y: Math.min(innerHeight - 120, Math.max(100, want.y - dy * k)) }
      // grab where the pull starts, so the hand ends on `want`
      await d.moveTo(start.x, start.y)
      await d.drag(dx * k, dy * k)
    }
  }
  /** Zoom (wheel notches at the cursor) until the map's zoom is at least `z`. */
  async function zoomTo(z, at) {
    const m = d.map()
    if (!m) return
    const dz = z - m.getZoom()
    if (Math.abs(dz) > 0.15) await d.zoom(dz, { at })
  }
  /** A box opened (desktop stack, or the phone's sheet). */
  const BOX = '.boxes .mapbox, .sheet .mapbox'
  async function closeBox() {
    if (isPhone()) return d.click('.sheet-x')
    return d.click('.boxes .mapbox .mb-x')
  }
  async function closeTray() {
    if (!document.querySelector('.slideover')) return
    await d.click(d.$('.slideover .so-close') ? '.slideover .so-close' : '.burger-btn')
    await pause(500, 800)
    await d.waitFor('.toolbar .lang-btn', 2000) // phones: the toolbar slides back in once the menu is gone
  }
  async function openTray(id) {
    if (!document.querySelector('.slideover')) {
      if (!(await d.click('.burger-btn'))) return false
      if (!(await d.waitFor('.tray-menu', 2500))) return false
      await pause(400, 800)
    } else if (!document.querySelector('.tray-menu')) {
      await d.click('.slideover .so-back')
      await d.waitFor('.tray-menu', 1500)
    }
    if (d.chance(0.35)) { await d.moveToEl('.tray-item', { slow: 1.3 }); await pause(150, 350) }
    return d.click(`.tray-item[data-id="${id}"]`)
  }
  /** Pick a free on-screen pin / icon of `layers` passing `test` and click it on the map. */
  async function clickFeature(layers, test, { tries = 3, zoomStep = 0.8 } = {}) {
    for (let i = 0; i < tries; i++) {
      await d.mapIdle()
      const found = d.featuresOnScreen(layers, test)
      if (found.length) {
        // nearest to the middle of the free area: what a person's eye lands on first
        const mid = { x: innerWidth * (isPhone() ? 0.5 : 0.6), y: innerHeight * 0.45 }
        found.sort((a, b) => Math.hypot(a.x - mid.x, a.y - mid.y) - Math.hypot(b.x - mid.x, b.y - mid.y))
        const c = found[Math.min(found.length - 1, Math.floor(d.r(0, Math.min(3, found.length))))]
        return d.clickMapPoint(c)
      }
      await d.zoom(i === 0 ? zoomStep : -zoomStep * 1.5)
    }
    return false
  }
  const truthy = (v) => v === true || v === 'true'

  // ================= 1. the start page and Syrenka Selects =================
  await scene('start page', async () => {
    if (view() !== 'landing') {
      await d.click('.mermaid-btn')
      await d.waitFor(() => view() === 'landing' && settled(), 5000)
    }
    await d.waitFor(() => document.querySelector('.landing .sel-card:not(.skeleton)'), 8000)
    await pause(900, 1400)
    await d.moveToEl('.hero-search', { slow: 1.4 })
    await d.linger(2, { over: '.hero-tiles .hero-tile' })
    const L = '.landing'
    await d.moveTo(innerWidth * d.r(0.42, 0.58), innerHeight * d.r(0.5, 0.62))
    await d.scroll(L, innerHeight * 0.55)
    await pause(400, 700)
    await d.scroll(L, innerHeight * 0.4)
    for (let i = 0; i < 2; i++) {
      await pause(600, 1100)
      const cards = onScreen('.sel-card:not(.skeleton)')
      if (cards.length) { await d.moveToEl(d.pick(cards), { slow: 1.35 }); await d.linger(d.r(1.2, 1.9)) }
      await d.scroll(L, innerHeight * d.r(0.35, 0.6))
    }
    await d.linger(1.2)
    const s = d.$(L)
    if (s) await d.scroll(s, -s.scrollTop, { burst: [480, 820], pause: [40, 140] })
    await pause(600, 1000)
  })

  // ================= 2. the search pill flies up, the map opens =================
  await scene('into the map', async () => {
    if (view() === 'landing' && !(await d.click('.hero-search .hero-go'))) await d.click('.landing-nav > button')
    await d.waitFor(() => view() === 'map' && settled() && d.$('.toolbar'), 8000)
    await d.sleep(d.r(1800, 2300))
    await d.mapIdle(3000)
  })
  if (!(await onMap())) return log

  // ================= 3. zoom and drag around the centre =================
  await scene('map moves', async () => {
    await d.linger(1.5)
    await d.zoom(d.r(1.1, 1.4))
    await d.drag(d.r(-200, -120), d.r(40, 110))
    await d.zoom(d.r(0.6, 0.9), { at: false })
    await d.linger(1.2, { zoomOk: true })
    await d.drag(d.r(150, 240), d.r(-90, -30))
    await d.zoom(-d.r(1.2, 1.6))
    await d.linger(1.5)
  })

  // ================= 4. search: Śródmieście, Nightlife, a nightlife event, "I'm going" =================
  await scene('search nightlife', async () => {
    if (!(await d.click(SEARCH))) return
    if (!(await d.waitFor('.evf', 2500))) return
    await d.linger(1, { over: '.evf-master' })
    // a clean canvas to start from: switches left on from before go off with the master switch
    for (let i = 0; i < 2 && document.querySelector('.evf-chip.on, .evf-row.on'); i++) await toggle('.evf-master', [700, 1100])
    if (await d.click('.evf .hs-where input')) {
      await pause(300, 600)
      await d.type('.evf .hs-where input', 'Śródmieście')
      const opts = () => onScreen('.where-pop .where-opt')
      const opt = await d.waitFor(() => opts().find((o) => o.querySelector('.t')?.textContent === 'Śródmieście') || opts().find((o) => /śródmieście/i.test(o.textContent)), 2500)
      await pause(500, 900)
      if (opt) await d.click(opt)
      await d.linger(0.9)
    }
    // the music group: look along its switches, then Nightlife
    await d.scrollIntoView('.evf-ghead[data-group="music"]', '.evf-scroll', { at: 0.3 })
    await pause(200, 400)
    await d.moveToEl('.evf-ghead[data-group="music"]', { slow: 1.3 })
    for (const id of ['concert', 'festival']) { await d.moveToEl(`.evf-chip[data-type="${id}"]`, { slow: 1.4 }); await pause(300, 600) }
    await toggle('.evf-chip[data-type="nightlife"]', [1200, 1800])
    await d.linger(1.5, { over: '.evf-chips .evf-chip' })
    if (!(await d.click('.evf-go'))) return
    // the results list: which of them is nightlife
    const list = await d.waitFor('.results .res-item, .sheet .res-item', 4000)
    if (!list) return
    await d.mapIdle(3000)
    await d.linger(1.5, { over: '.res-item' })
    const scroller = scrollerOf(list)
    if (scroller) { await d.moveToEl(list, { slow: 1.2 }); await d.scroll(scroller, d.r(120, 260)); await pause(300, 600) }
    const label = typeLabel('nightlife')
    const items = onScreen('.results .res-item, .sheet .res-item')
    const night = items.find((it) => it.querySelector('.s span')?.textContent === label) || items[0]
    if (!night) return
    await d.click(night)
    if (!(await d.waitFor(BOX, 3000))) return
    await d.mapIdle(2500)
    await d.linger(2.5, { over: '.mapbox h2' })
    // "I'm going, come with me" / "Ask to join": only pretended, nothing goes to the server
    const cta = d.$('.mapbox .blk.social .btn')
    if (cta) { await d.moveToEl('.mapbox .blk.social', { slow: 1.3 }); await pause(400, 700); await d.fakeClick(cta); await d.linger(1.5) }
    await closeBox()
    await pause(500, 900)
    if (!isPhone() && (await d.click('.close-all'))) await pause(600, 900)
    else if (isPhone() && d.$('.sheet-x')) await d.click('.sheet-x')
    await d.linger(1.5)
  })

  // ================= 5. the pin box: a few kinds off and on again =================
  await scene('pin box', async () => {
    await inPinBox(async () => {
      await d.linger(1, { over: '.pin-menu .pm-opt' })
      await toggle(PIN_OPT('food'), [500, 900])
      await toggle(PIN_OPT('sights'), [1800, 2600])
      await toggle(PIN_OPT('sights'))
      await toggle(PIN_OPT('food'), [700, 1100])
    })
    await d.linger(1, { zoomOk: true })
  })

  // ================= 6. the event search's own switches =================
  await scene('event search switches', async () => {
    if (!(await d.click(SEARCH))) return
    if (!(await d.waitFor('.evf', 2500))) return
    await pause(500, 800)
    await toggle('.evf-master', [1600, 2200]) // all on
    await toggle('.evf-master', [900, 1300]) // all off again
    await d.scrollIntoView('.evf-ghead[data-group="sights"]', '.evf-scroll', { at: 0.3 })
    await toggle('.evf-ghead[data-group="sights"]', [1300, 1900])
    await d.linger(1.2, { over: '.evf-chip' })
    await clickEmptyMap()
    await d.linger(1)
  })

  // ================= 7. "Open now" =================
  await scene('open now', async () => {
    await inPinBox(async () => {
      await toggle(PIN_OPT('open'), [1800, 2500])
      await d.linger(0.8)
      await toggle(PIN_OPT('open'))
    })
  })

  // ================= 8. the weather pill =================
  await scene('weather', async () => {
    if (!(await d.click('.cond-chip'))) return
    if (await d.waitFor('.cond-pop', 1500)) await d.linger(3, { over: '.cond-pop .cond-row' })
    await d.click('.cond-chip')
  })

  // ================= 9. a place's opening hours =================
  await scene('opening hours', async () => {
    await dragToward(CENTRUM, 2)
    await zoomTo(14.6)
    const opened = await clickFeature(['wl-dots'], (f) => f.properties.kind === 'place' && f.properties.opening_hours && f.properties.opening_hours !== 'null')
    if (!opened || !(await d.waitFor(BOX, 2500))) return
    await d.mapIdle(2500)
    await d.linger(1.5, { over: '.mapbox h2' })
    if (await d.click('.mapbox .week-hours summary')) { await d.linger(2.5, { over: '.mapbox .week-hours li' }); await d.click('.mapbox .week-hours summary') }
    await pause(300, 600)
    await closeBox()
  })

  // ================= 10. busy areas =================
  await scene('busy areas', async () => {
    await zoomTo(12.8)
    await d.linger(1, { zoomOk: true })
    await inPinBox(async () => {
      await toggle(PIN_OPT('busy'), [1600, 2100])
      await toggle(PIN_OPT('busy'), [1000, 1400])
    })
  })

  // ================= 11. walking routes =================
  await scene('walking routes', async () => {
    const m = d.map()
    if (!m?.getLayer('wl-walks-hit')) return
    const opened = await clickFeature(['wl-walks-hit'], () => true, { zoomStep: -0.8 })
    if (!opened || !(await d.waitFor(BOX, 2500))) return
    await d.mapIdle(3000)
    await d.linger(3.5, { over: '.mapbox h2' })
    await closeBox()
  })

  // ================= 12. metro stations =================
  await scene('metro stations', async () => {
    const m = d.map()
    const isMetro = (f) => f.properties.amenity === 'transit' && truthy(f.properties.metro)
    // only when the city's stations are loaded (GET /places?category=transit); else just their switch
    if (m?.getSource('wl-amenities') && m.querySourceFeatures('wl-amenities').some(isMetro)) {
      await dragToward(CENTRUM, 3)
      await zoomTo(14.4)
      if (await clickFeature(['wl-amenities'], isMetro, { zoomStep: 0.6 }) && (await d.waitFor(BOX, 2500))) {
        await d.mapIdle(2500)
        await d.linger(3.5, { over: '.mapbox h2' })
        await closeBox()
        return
      }
    }
    await inPinBox(async () => {
      await d.linger(1.5, { over: PIN_OPT('transit') })
      await toggle(PIN_OPT('transit'), [1200, 1700])
      await toggle(PIN_OPT('transit'))
    })
  })

  // ================= 13. the slide-over: Profile, Favourites, Messages, Settings / Data sources =================
  await scene('slide-over', async () => {
    if (!(await openTray('profile'))) return
    await pause(1000, 1500)
    await d.linger(1, { over: '.slideover .sp-head' })
    await d.moveToEl('.slideover .so-body', { slow: 1.3 })
    await d.scroll('.slideover .sp-scroll', d.r(250, 420))
    await d.linger(1)
    if (await d.click('.slideover .so-link')) { await d.linger(1.8); await d.click('.slideover .so-back') }
    else await d.click('.slideover .so-back')
    await d.waitFor('.tray-menu', 1500)
    await pause(400, 800)
    if (await openTray('messages')) { await d.linger(1.8, { over: '.slideover .sp-row' }); await d.click('.slideover .so-back') }
    await d.waitFor('.tray-menu', 1500)
    if (await openTray('settings')) {
      await pause(900, 1300)
      await d.moveToEl('.slideover .sp-scroll', { slow: 1.3 })
      await d.scroll('.slideover .sp-scroll', d.r(380, 520))
      await d.linger(1.8, { over: '.slideover .sp-row' })
      await d.scroll('.slideover .sp-scroll', -2000, { burst: [400, 700], pause: [40, 140] })
    }
    await closeTray()
  })

  // ================= 14. the language switch =================
  await scene('language', async () => {
    const was = getLang(), other = was === 'pl' ? 'en' : 'pl'
    if (!(await d.click('.lang-btn'))) return
    if (!(await d.waitFor('.lang-menu', 1500))) return
    await pause(400, 800)
    await d.click(`.lang-menu [data-lang="${other}"]`)
    await d.linger(2, { over: '.toolbar .tb' })
    await inPinBox(() => d.linger(1.5, { over: '.pin-menu .pm-opt' })) // the same box, in the other language
    if (!(await d.click('.lang-btn'))) return
    if (await d.waitFor('.lang-menu', 1500)) await d.click(`.lang-menu [data-lang="${was}"]`)
    await d.linger(1.5)
  })

  // ================= 15. dark mode =================
  await scene('dark mode', async () => {
    if (!(await d.click('.toolbar [data-tb="dark"]'))) return
    await d.linger(2.5, { zoomOk: true })
    const p = d.mapSpot()
    await d.moveTo(p.x, p.y)
    await d.drag(d.r(-140, 140), d.r(-80, 80))
    await d.linger(1.5)
    await d.click('.toolbar [data-tb="dark"]')
    await d.linger(1.5)
  })

  // ================= 16. the time window =================
  await scene('time window', async () => {
    const was = document.querySelector('.seg-opt[aria-checked="true"]')?.dataset.window
    for (const w of ['today', 'weekend', 'week', 'month']) {
      if (await d.click(`.seg [data-window="${w}"]`)) await d.linger(d.r(1.3, 1.9), { zoomOk: w === 'week' })
    }
    if (was && was !== 'month') await d.click(`.seg [data-window="${was}"]`)
  })

  // ================= 17. Create event: a few fields, then cancel =================
  await scene('create event', async () => {
    if (!(await openTray('create'))) return
    if (!(await d.waitFor('.create-panel', 2500))) return
    await pause(800, 1300)
    // logged out the panel is a login form (its fields are .ce-input too): never type there
    const inputs = document.querySelector('.create-panel .login-form') ? [] : document.querySelectorAll('.create-panel .ce-scroll > .ce-field .ce-input')
    if (inputs.length) {
      const pl = getLang() === 'pl'
      await d.click(inputs[0])
      await d.type(inputs[0], pl ? 'Spacer nad Wisłą' : 'A walk along the Vistula')
      await pause(500, 900)
      if (inputs[1] && (await d.click(inputs[1]))) await d.type(inputs[1], pl ? 'Spokojnym tempem, dla każdego' : 'Easy pace, everyone welcome', { typo: 0.3 })
      await pause(600, 1000)
      await d.scrollIntoView('.create-panel .ce-types', '.create-panel .ce-scroll', { at: 0.2 })
      await toggle('.create-panel .ce-types [aria-pressed]:nth-child(' + (8 + Math.floor(d.r(0, 6))) + ')')
      await d.linger(2)
      await d.scrollIntoView('.create-panel .ce-audience', '.create-panel .ce-scroll', { at: 0.3 })
      await d.linger(2.5, { over: '.create-panel .ce-aud' })
    } else {
      await d.linger(3, { over: '.create-panel .sp-head' }) // logged out: the panel asks to log in first
    }
    await d.click('.create-panel .sp-head .close-btn') // cancel: nothing is created
    await pause(600, 1000)
  })

  // ================= 18. the people on the map =================
  await scene('people', async () => {
    if (await d.click('.people-btn')) {
      if (await d.waitFor('.people-menu', 1500)) await d.linger(2.2, { over: '.people-menu .pm-opt' })
      await d.click('.people-btn')
    }
    await zoomTo(12.6)
    await d.mapIdle()
    const face = () => onScreen('.person-marker .pr-av').find((el) => { const b = el.getBoundingClientRect(); return el.contains(document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2)) })
    const pr = face()
    if (!pr) return
    await d.moveToEl(pr, { slow: 1.2 })
    await d.linger(1.5)
    await d.click(pr)
    if (await d.waitFor('.slideover', 2500)) { await pause(1500, 2200); await d.linger(3) }
    await closeTray()
  })

  // ================= 19. Syrenka Selects in the side bar =================
  await scene('selects in the tray', async () => {
    if (!(await openTray('selects'))) return
    const item = await d.waitFor('.slideover .sr-item', 2500)
    if (!item) { await closeTray(); return }
    await pause(800, 1200)
    await d.moveToEl(item, { slow: 1.3 })
    const sc = scrollerOf(item)
    if (sc) {
      await d.scroll(sc, d.r(300, 460))
      await pause(500, 900)
      const vis = onScreen('.slideover .sr-item')
      if (vis.length) { await d.moveToEl(d.pick(vis), { slow: 1.4 }); await d.linger(d.r(1.2, 2)) }
      await d.scroll(sc, -sc.scrollTop, { burst: [400, 700], pause: [40, 140] })
    }
    await closeTray()
  })

  // ================= finale: wander a little until five minutes, then the whole city =================
  await scene('finale', async () => {
    while (elapsed() < TARGET_MS - 20000) {
      await d.linger(d.r(2.5, 4), { zoomOk: true })
      if (d.chance(0.6)) await d.drag(d.r(-180, 180), d.r(-100, 100))
    }
    await d.click('.toolbar [data-tb="home"]')
    await d.mapIdle(3000)
    await d.linger(4)
    await d.moveToEl('.toolbar', { slow: 1.6 })
    await d.sleep(1500)
  })

  return log
}
