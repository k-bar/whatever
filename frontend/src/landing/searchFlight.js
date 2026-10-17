/**
 * The search pill's flight between the start page and the map.
 *
 * One calm "push": it leaves confidently, decelerates and stops — no spring, no overshoot — and it is
 * exactly the same motion in both directions (start page -> map, map -> start page).
 *
 * While it flies, both real pills are hidden (`.app.flying`) and a lightweight stand-in travels between
 * their boxes: one fixed element with `contain: strict`, so resizing it never re-lays out anything else.
 * The caller keeps the map still until it lands, so nothing competes with the motion for frames.
 */

export const FLIGHT_MS = 700
// a "push": eases off the mark, moves confidently through the middle, then stops firmly. No overshoot.
export const FLIGHT_EASE = 'cubic-bezier(0.4, 0, 0.2, 1)'

const SEARCH_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'

const frame = (r) => ({ transform: `translate3d(${r.left}px, ${r.top}px, 0)`, width: `${r.width}px`, height: `${r.height}px` })

/** Fly the stand-in pill from one box to another. Resolves when it has landed (the stand-in is then removed). */
export function flySearch(from, to, { text = '', placeholder = '', reduceMotion = false } = {}) {
  if (!from || !to) return Promise.resolve()
  const ghost = document.createElement('div')
  ghost.className = 'search-ghost'
  ghost.innerHTML = `<span class="sg-text"></span><span class="sg-go">${SEARCH_ICON}</span>`
  const label = ghost.firstChild
  label.textContent = text || placeholder
  label.classList.toggle('filled', Boolean(text))
  Object.assign(ghost.style, frame(to)) // the resting state once the animation ends
  document.body.appendChild(ghost)
  const duration = reduceMotion ? 0 : FLIGHT_MS
  const anim = ghost.animate([frame(from), frame(to)], { duration, easing: FLIGHT_EASE, fill: 'both' })
  // a background tab pauses animations: hand over on time anyway, so the real pills never stay hidden
  const deadline = new Promise((resolve) => setTimeout(resolve, duration + 250))
  return Promise.race([anim.finished.catch(() => {}), deadline]).then(() => {
    anim.finish()
    // let the real pill paint in its spot first, then drop the stand-in: no flicker at the hand-over
    // (the timer covers background tabs, which draw no frames)
    const drop = () => ghost.remove()
    requestAnimationFrame(() => requestAnimationFrame(drop))
    setTimeout(drop, 150)
  })
}
