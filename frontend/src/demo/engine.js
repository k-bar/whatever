/**
 * The demo's hands: a drawn mouse cursor that glides over the real interface and clicks, scrolls, drags,
 * zooms and types like a person would. Every action is real (DOM events on the real elements, the real
 * MapLibre map); only the cursor is drawn. All randomness comes from one seed, so a rehearsal and the
 * presentation look the same, and every duration is divided by `speed` (rehearse at 4×, present at 1×).
 *
 * Any action throws Stopped once stop() was called; the tour (demo/tour.js) just lets it bubble up.
 */

export class Stopped extends Error {}

/** mulberry32: small, fast, seedable. */
function seeded(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v))
// minimum-jerk profile, slightly front-loaded: a hand speeds up quickly and settles slowly onto the target
const handEase = (t) => { const u = Math.pow(t, 0.82); return u * u * u * (10 - 15 * u + 6 * u * u) }
const easeOut = (t) => 1 - Math.pow(1 - t, 3)
const bez = (a, b, c, d, t) => { const s = 1 - t; return s * s * s * a + 3 * s * s * t * b + 3 * s * t * t * c + t * t * t * d }

const CURSOR_SVG = '<svg width="26" height="30" viewBox="0 0 26 30" aria-hidden="true">'
  + '<path d="M3 2 L3 23.5 L8.6 18.4 L12.4 27.2 L16.4 25.4 L12.7 16.9 L20.4 16.6 Z" fill="#fff" stroke="#111" stroke-width="1.7" stroke-linejoin="round"/></svg>'

const ancestors = (el) => { const out = []; for (let n = el; n && n.nodeType === 1; n = n.parentElement) out.push(n); return out }
const visible = (el) => { if (!el?.isConnected) return false; const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth }

export function createDemo({ seed = 1, speed = 1, getMap }) {
  const rand = seeded(seed)
  let stopped = false
  const pending = new Set() // { cancel } for every sleep / animation in flight
  const missed = [] // selectors a step looked for and didn't find (skipped): for rehearsals
  const miss = (sel) => { if (typeof sel === 'string' && missed.length < 200) missed.push(sel); return null }

  // ---------- randomness ----------
  const r = (a, b) => a + rand() * (b - a)
  const chance = (p) => rand() < p
  const pick = (arr) => arr[Math.floor(rand() * arr.length)]

  // ---------- time ----------
  const check = () => { if (stopped) throw new Stopped() }
  /** Wait `ms` (at speed 1). Rejects with Stopped the moment the demo is stopped. */
  const sleep = (ms) => new Promise((resolve, reject) => {
    check()
    const p = { cancel: () => { clearTimeout(id); reject(new Stopped()) } }
    const id = setTimeout(() => { pending.delete(p); resolve() }, ms / speed)
    pending.add(p)
  })
  // one frame: rAF, or a timer when the page is hidden (rAF sleeps there and would stall the tour)
  const frame = () => new Promise((resolve) => {
    let done = false
    const go = () => { if (!done) { done = true; cancelAnimationFrame(a); clearTimeout(b); resolve() } }
    const a = requestAnimationFrame(go)
    const b = setTimeout(go, 40)
  })
  /** Run fn(t) with t from 0 to 1 over `ms` (at speed 1). */
  async function animate(ms, fn) {
    const t0 = performance.now(), dur = Math.max(1, ms / speed)
    for (;;) {
      check()
      const t = Math.min(1, (performance.now() - t0) / dur)
      fn(t)
      if (t >= 1) return
      await frame()
    }
  }

  // ---------- the cursor ----------
  const el = document.createElement('div')
  el.className = 'demo-cursor'
  el.innerHTML = `<span class="demo-ripple"></span><span class="demo-arrow">${CURSOR_SVG}</span>`
  document.body.appendChild(el)
  const pos = { x: innerWidth * r(0.45, 0.6), y: innerHeight * r(0.55, 0.7) }
  const place = () => { el.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)` }
  place()
  requestAnimationFrame(() => el.classList.add('on'))

  // pointerenter / leave on every ancestor entered or left, like a real mouse (framer's whileHover listens to these)
  let hovered = null, lastHover = 0
  const mouseInit = (x, y, extra) => ({ bubbles: true, cancelable: true, composed: true, view: window, clientX: x, clientY: y, screenX: x, screenY: y, pointerId: 1, pointerType: 'mouse', isPrimary: true, ...extra })
  function hoverAt(x, y, force) {
    const now = performance.now()
    if (!force && now - lastHover < 45) return
    lastHover = now
    const hit = document.elementFromPoint(x, y)
    if (hit === hovered) { hit?.dispatchEvent(new PointerEvent('pointermove', mouseInit(x, y))); return }
    const before = hovered ? ancestors(hovered) : [], after = hit ? ancestors(hit) : []
    const left = before.filter((n) => !after.includes(n)), entered = after.filter((n) => !before.includes(n)).reverse()
    if (hovered) { hovered.dispatchEvent(new PointerEvent('pointerout', mouseInit(x, y))); hovered.dispatchEvent(new MouseEvent('mouseout', mouseInit(x, y))) }
    for (const n of left) { n.dispatchEvent(new PointerEvent('pointerleave', { ...mouseInit(x, y), bubbles: false })); n.dispatchEvent(new MouseEvent('mouseleave', { ...mouseInit(x, y), bubbles: false })) }
    if (hit) { hit.dispatchEvent(new PointerEvent('pointerover', mouseInit(x, y))); hit.dispatchEvent(new MouseEvent('mouseover', mouseInit(x, y))) }
    for (const n of entered) { n.dispatchEvent(new PointerEvent('pointerenter', { ...mouseInit(x, y), bubbles: false })); n.dispatchEvent(new MouseEvent('mouseenter', { ...mouseInit(x, y), bubbles: false })) }
    hit?.dispatchEvent(new PointerEvent('pointermove', mouseInit(x, y)))
    hovered = hit
  }

  /** Glide to (x, y) on a gently curved path; long moves sometimes overshoot a touch and correct. */
  async function moveTo(x, y, { slow = 1, onStep } = {}) {
    x = clamp(x, 2, innerWidth - 4); y = clamp(y, 2, innerHeight - 4)
    const from = { ...pos }, dx = x - from.x, dy = y - from.y, d = Math.hypot(dx, dy)
    if (d < 1.5) return
    const over = d > 280 && chance(0.35)
    const tx = over ? x + (dx / d) * r(7, 16) : x, ty = over ? y + (dy / d) * r(7, 16) : y
    const nx = -dy / d, ny = dx / d
    const bend = clamp(r(-0.2, 0.2) * d, -150, 150)
    const c1 = { x: from.x + dx * r(0.2, 0.4) + nx * bend, y: from.y + dy * r(0.2, 0.4) + ny * bend }
    const c2 = { x: from.x + dx * r(0.65, 0.85) + nx * bend * 0.35, y: from.y + dy * r(0.65, 0.85) + ny * bend * 0.35 }
    const ms = (230 + 135 * Math.log2(1 + d / 28)) * r(0.85, 1.25) * slow
    await animate(ms, (t) => {
      const e = handEase(t)
      const px = pos.x, py = pos.y
      pos.x = bez(from.x, c1.x, c2.x, tx, e); pos.y = bez(from.y, c1.y, c2.y, ty, e)
      place(); onStep?.(pos.x - px, pos.y - py); hoverAt(pos.x, pos.y)
    })
    if (over) {
      await sleep(r(40, 110))
      const sx = pos.x, sy = pos.y
      await animate(r(140, 230) * slow, (t) => { const e = easeOut(t), px = pos.x, py = pos.y; pos.x = sx + (x - sx) * e; pos.y = sy + (y - sy) * e; place(); onStep?.(pos.x - px, pos.y - py) })
    }
    hoverAt(pos.x, pos.y, true)
  }

  // ---------- elements ----------
  const $ = (sel, root = document) => (typeof sel === 'string' ? [...root.querySelectorAll(sel)].find(visible) || null : visible(sel) ? sel : null)
  /** Wait up to `ms` for an element to be on screen; null if it never comes (the step is then skipped). */
  async function waitFor(sel, ms = 3000) {
    const t0 = performance.now()
    for (;;) {
      const found = typeof sel === 'function' ? sel() : $(sel)
      if (found) return found
      if (performance.now() - t0 > ms) return null
      await sleep(100 * speed) // real time: the app answers at its own pace, whatever the demo's speed
    }
  }
  /** A natural point inside an element: near the middle, never dead centre, kept off the edges. */
  function pointIn(target, { spread = 0.22 } = {}) {
    const b = target.getBoundingClientRect()
    const at = (sx, sy) => ({
      x: clamp(b.left + b.width * (0.5 + sx), b.left + Math.min(6, b.width / 3), b.right - Math.min(6, b.width / 3)),
      y: clamp(b.top + b.height * (0.5 + sy), b.top + Math.min(5, b.height / 3), b.bottom - Math.min(5, b.height / 3)),
    })
    const first = at(r(-spread, spread), r(-spread, spread) * 0.8)
    // aim at a part of it that is really on top (a toolbar or panel may cover some of it)
    const free = (p) => p.x >= 0 && p.y >= 0 && p.x < innerWidth && p.y < innerHeight && target.contains(document.elementFromPoint(p.x, p.y))
    if (free(first)) return first
    for (let i = 0; i < 14; i++) { const p = at(r(-0.45, 0.45), r(-0.45, 0.45)); if (free(p)) return p }
    return first
  }
  async function moveToEl(sel, opts) {
    const target = $(sel)
    if (!target) return miss(sel)
    const p = pointIn(target, opts)
    await moveTo(p.x, p.y, opts)
    return target
  }

  // ---------- press / click ----------
  // a real press on something that can't take focus moves the focus off the field that had it
  const blurAway = (at) => { const a = document.activeElement; if (a && a !== document.body && !a.contains(at)) a.blur() }
  /** Focus a field. A window without the system focus (a rehearsal in a background window) sends no focus
   *  events, so the app wouldn't notice: then they are sent by hand. */
  function focusField(f) {
    if (document.activeElement === f && document.hasFocus()) return
    const prev = document.activeElement
    f.focus({ preventScroll: true })
    if (document.hasFocus()) return
    if (prev && prev !== f && prev !== document.body) { prev.dispatchEvent(new FocusEvent('blur')); prev.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: f })) }
    f.dispatchEvent(new FocusEvent('focus')); f.dispatchEvent(new FocusEvent('focusin', { bubbles: true, relatedTarget: prev }))
  }
  const pressAnim = () => { el.classList.remove('press'); void el.offsetWidth; el.classList.add('press'); setTimeout(() => el.classList.remove('press'), 420) }
  function fire(target, type, Ctor = MouseEvent, extra) { target.dispatchEvent(new Ctor(type, mouseInit(pos.x, pos.y, extra))) }
  /** Press and release at the cursor, on what's under it (or `target` when something sits on top). */
  async function pressHere(target, { hold = r(70, 130) } = {}) {
    const hit = document.elementFromPoint(pos.x, pos.y)
    const at = target && !(hit && target.contains(hit)) ? target : hit
    if (!at) return null
    pressAnim()
    fire(at, 'pointerdown', PointerEvent, { button: 0, buttons: 1 }); fire(at, 'mousedown', MouseEvent, { button: 0, buttons: 1 })
    const field = at.closest('input, textarea, [contenteditable]')
    if (field) focusField(field)
    else blurAway(at)
    await sleep(hold)
    fire(at, 'pointerup', PointerEvent, { button: 0, buttons: 0 }); fire(at, 'mouseup', MouseEvent, { button: 0, buttons: 0 })
    fire(at, 'click', MouseEvent, { button: 0, buttons: 0, detail: 1 })
    return at
  }
  /** Move to an element and click it. false when it isn't there (the caller carries on). */
  async function click(sel, { before = [90, 260], after = [160, 420], ...opts } = {}) {
    check()
    const target = await moveToEl(sel, opts)
    if (!target) return false
    await sleep(r(...before))
    await pressHere(target)
    await sleep(r(...after))
    return true
  }
  /** Looks like a click (cursor and button press in) but sends nothing: for buttons that would write to the server. */
  async function fakeClick(sel, opts) {
    const target = await moveToEl(sel, opts)
    if (!target) return false
    await sleep(r(120, 280))
    pressAnim()
    target.classList.add('demo-pressed')
    await sleep(r(130, 190))
    target.classList.remove('demo-pressed')
    await sleep(r(250, 500))
    return true
  }

  // ---------- typing ----------
  const nativeSetter = (f) => Object.getOwnPropertyDescriptor(Object.getPrototypeOf(f), 'value').set
  const NEIGHBOURS = { a: 's', s: 'a', d: 's', r: 't', m: 'n', n: 'm', o: 'i', i: 'o', e: 'w', c: 'x', t: 'r', l: 'k', u: 'y' }
  function setValue(f, v) {
    nativeSetter(f).call(f, v)
    f.dispatchEvent(new InputEvent('input', { bubbles: true, data: null, inputType: 'insertText' }))
  }
  /** Type into a field letter by letter, in little bursts, maybe with one slip that gets backspaced. */
  async function type(sel, text, { typo = 0.5 } = {}) {
    const f = $(sel)
    if (!f) return !!miss(sel)
    if (document.activeElement !== f) focusField(f)
    const slipAt = chance(typo) ? 2 + Math.floor(rand() * Math.max(1, text.length - 3)) : -1
    for (let i = 0; i < text.length; i++) {
      check()
      if (i === slipAt && NEIGHBOURS[text[i].toLowerCase()]) {
        setValue(f, f.value + NEIGHBOURS[text[i].toLowerCase()])
        await sleep(r(260, 480))
        setValue(f, f.value.slice(0, -1))
        await sleep(r(120, 220))
      }
      setValue(f, f.value + text[i])
      await sleep(chance(0.12) ? r(260, 520) : r(65, 170))
    }
    return true
  }
  async function clearField(sel) {
    const f = $(sel)
    if (!f) return false
    while (f.value) { setValue(f, f.value.slice(0, -1)); await sleep(r(30, 60)) }
    return true
  }

  // ---------- scrolling ----------
  /** Scroll an element by `amount` px in wheel-like bursts with small pauses, like a hand on a mouse wheel. */
  async function scroll(sel, amount, { burst = [140, 320], pause = [90, 520] } = {}) {
    const s = $(sel)
    if (!s) return !!miss(sel)
    let left = amount
    while (Math.abs(left) > 4) {
      check()
      const step = Math.sign(left) * Math.min(Math.abs(left), r(...burst))
      const from = s.scrollTop, to = clamp(from + step, 0, s.scrollHeight - s.clientHeight)
      if (Math.abs(to - from) < 1) break
      await animate(r(260, 460), (t) => s.scrollTo({ top: from + (to - from) * easeOut(t), behavior: 'instant' }))
      hoverAt(pos.x, pos.y, true)
      left -= step
      await sleep(r(...pause))
    }
    return true
  }
  /** Scroll so an element sits comfortably inside its scroller. */
  async function scrollIntoView(sel, scroller, { at = 0.35 } = {}) {
    const target = $(sel) || (typeof sel === 'string' ? document.querySelector(sel) : sel)
    const s = $(scroller)
    if (!target || !s) return false
    const delta = target.getBoundingClientRect().top - s.getBoundingClientRect().top - s.clientHeight * at
    return scroll(s, delta)
  }

  // ---------- the map ----------
  const map = () => getMap?.() || null
  /** A point in the open part of the map: clear of the search panel, the boxes and the toolbar. */
  function mapSpot() {
    const phone = innerWidth < 768
    const box = document.querySelector('.boxes')?.getBoundingClientRect()
    const right = !phone && box?.width && box.left > innerWidth * 0.5 ? box.left - 30 : innerWidth * (phone ? 0.85 : 0.82)
    const left = phone ? innerWidth * 0.15 : Math.min(right - 80, Math.max(innerWidth * 0.38, 470))
    return { x: r(left, right), y: innerHeight * r(phone ? 0.3 : 0.28, phone ? 0.55 : 0.7) }
  }
  const lngLatAt = (m, x, y) => { const b = m.getCanvas().getBoundingClientRect(); return m.unproject([x - b.left, y - b.top]) }
  /** Wait for the map to stop moving (a fly / fit), max `ms`. */
  async function mapIdle(ms = 2500) {
    const m = map()
    if (!m) return
    const t0 = performance.now()
    while (m.isMoving() && performance.now() - t0 < ms) await sleep(100 * speed)
  }
  /** Zoom by `dz` around the cursor, in mouse-wheel notches. */
  async function zoom(dz, { at } = {}) {
    const m = map()
    if (!m) return false
    if (at !== false) { const p = at || mapSpot(); await moveTo(p.x, p.y) }
    await sleep(r(150, 350))
    const notches = Math.max(1, Math.round(Math.abs(dz) / r(0.35, 0.55)))
    for (let i = 0; i < notches; i++) {
      check()
      const z = clamp(m.getZoom() + dz / notches, m.getMinZoom(), m.getMaxZoom())
      m.easeTo({ zoom: z, around: lngLatAt(m, pos.x, pos.y), duration: r(260, 380) / speed, easing: easeOut })
      await sleep(i === notches - 1 ? r(380, 520) : r(110, 260))
    }
    return true
  }
  /** Grab the map at the cursor and drag it by (dx, dy), then let go with a little glide. */
  async function drag(dx, dy) {
    const m = map()
    if (!m) return false
    await sleep(r(120, 260))
    pressAnim(); el.classList.add('grab')
    await sleep(r(80, 150))
    let vx = 0, vy = 0
    const target = { x: pos.x + dx, y: pos.y + dy }
    await moveTo(target.x, target.y, { slow: r(1.4, 1.9), onStep: (sx, sy) => { if (sx || sy) { m.panBy([-sx, -sy], { animate: false }); vx = sx; vy = sy } } })
    el.classList.remove('grab')
    const k = r(5, 9)
    m.panBy([-vx * k, -vy * k], { duration: r(420, 620) / speed, easing: easeOut })
    await sleep(r(400, 650))
    return true
  }
  /** Rendered features of `layers` whose on-screen point is free (nothing of ours drawn over it). */
  function featuresOnScreen(layers, test = () => true) {
    const m = map()
    if (!m) return []
    const have = layers.filter((l) => m.getLayer(l))
    if (!have.length) return []
    const canvas = m.getCanvas(), b = canvas.getBoundingClientRect()
    const seen = new Set(), out = []
    for (const f of m.queryRenderedFeatures({ layers: have })) {
      if (!test(f)) continue
      const key = f.id ?? JSON.stringify(f.properties).slice(0, 80)
      if (seen.has(key)) continue
      seen.add(key)
      const c = f.geometry.type === 'Point' ? f.geometry.coordinates : f.geometry.type === 'LineString' ? f.geometry.coordinates[Math.floor(f.geometry.coordinates.length / 2)] : null
      if (!c) continue
      const p = m.project(c)
      const x = p.x + b.left, y = p.y + b.top
      if (x < 20 || y < 20 || x > innerWidth - 20 || y > innerHeight - 20) continue
      const hit = document.elementFromPoint(x, y)
      if (hit !== canvas) continue // under a panel, a box or the toolbar
      out.push({ f, x, y })
    }
    return out
  }
  /** Click the map's canvas at the cursor, as a real click (MapLibre picks the pin under it). */
  async function clickMap() {
    const m = map()
    if (!m) return false
    await sleep(r(100, 240))
    const c = m.getCanvas()
    pressAnim()
    blurAway(c)
    fire(c, 'pointerdown', PointerEvent, { button: 0, buttons: 1 }); fire(c, 'mousedown', MouseEvent, { button: 0, buttons: 1 })
    await sleep(r(60, 110))
    fire(c, 'pointerup', PointerEvent, { button: 0 }); fire(c, 'mouseup', MouseEvent, { button: 0 })
    fire(c, 'click', MouseEvent, { button: 0, detail: 1 })
    await sleep(r(200, 400))
    return true
  }
  /** Bring the cursor to the closest of `candidates` ({ x, y }) and click it on the map. */
  async function clickMapPoint(c) {
    await moveTo(c.x, c.y)
    await sleep(r(80, 200))
    return clickMap()
  }

  // ---------- idling ----------
  /** About four seconds at a new place: sometimes still, sometimes a slow drift, a wiggle or a small zoom. */
  async function linger(sec = 4, { zoomOk = false, over } = {}) {
    const end = performance.now() + (sec * r(0.8, 1.2) * 1000) / speed
    while (performance.now() < end) {
      const left = (end - performance.now()) * speed
      const mode = pick(zoomOk ? ['still', 'drift', 'drift', 'wiggle', 'zoom'] : ['still', 'drift', 'drift', 'wiggle'])
      if (mode === 'still' || left < 700) await sleep(Math.min(left, r(700, 1600)))
      else if (mode === 'drift') {
        const a = r(0, Math.PI * 2), dist = r(14, 60)
        await moveTo(pos.x + Math.cos(a) * dist, pos.y + Math.sin(a) * dist, { slow: r(2, 3.2) })
        await sleep(Math.min(left, r(250, 900)))
      } else if (mode === 'wiggle') {
        const t = over && $(over)
        if (t) await moveToEl(t, { slow: 1.6, spread: 0.35 })
        else for (let i = 0; i < 2; i++) await moveTo(pos.x + r(-22, 22), pos.y + r(-12, 12), { slow: 1.4 })
        await sleep(Math.min(left, r(200, 600)))
      } else if (mode === 'zoom' && map()) {
        await zoom(pick([-0.4, 0.3, 0.45, -0.3]), { at: false })
      }
    }
  }

  function stop() {
    if (stopped) return
    stopped = true
    for (const p of pending) p.cancel()
    pending.clear()
    el.classList.remove('on', 'grab')
    el.classList.add('off')
    setTimeout(() => el.remove(), 400)
  }

  return {
    r, chance, pick, sleep, check, animate, speed, missed, get stopped() { return stopped }, pos,
    $, waitFor, pointIn, moveTo, moveToEl, hoverAt, click, fakeClick, pressHere, type, clearField, scroll, scrollIntoView,
    map, mapSpot, mapIdle, zoom, drag, featuresOnScreen, clickMap, clickMapPoint, linger, stop,
  }
}
