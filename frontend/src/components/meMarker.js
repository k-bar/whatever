import mermaidSvg from '../assets/mermaid.svg'

/**
 * The "you are here" marker, one look per option of `meStyle` (Interface editor -> Map design).
 * Same family as the start page's people bubbles: accent teardrop, white rim, white face with a figure.
 * Each builder returns the marker's inner HTML; the 44px box is centred on the position, so pins sit
 * with their tip on the centre and round markers sit on it directly.
 */

const PIN = '<path d="M20 50.5S4 32.2 4 20a16 16 0 1 1 32 0c0 12.2-16 30.5-16 30.5z"/>'
const PERSON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7.6" r="4.3"/><path d="M3.4 22c0-5 3.9-8.4 8.6-8.4s8.6 3.4 8.6 8.4z"/></svg>'
const RINGS = '<span class="ring"></span><span class="ring r2"></span>'
const GROUND = '<span class="ground"></span>'

const pin = (face) => `<span class="me-pin"><svg class="me-shape" viewBox="0 0 40 52" aria-hidden="true">${PIN}</svg><span class="me-face">${face}</span></span>`
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

export const ME_STYLES = {
  // accent pin with a person in a white face, pulsing where it touches the map
  person: () => RINGS + GROUND + pin(PERSON),
  // the same pin with a small white "You are here" tag beside it
  tag: (label = 'You are here') => RINGS + GROUND + pin(PERSON) + `<span class="me-label">${esc(label)}</span>`,
  // white pin with an accent rim, the Syrenka shield in the face
  syrenka: () => RINGS + GROUND + pin(`<img src="${mermaidSvg}" alt="" draggable="false">`),
  // round avatar: white face with a figure, accent ring, wide soft halo
  avatar: () => '<span class="halo"></span>' + RINGS + `<span class="me-face">${PERSON}</span>`,
  // small accent dot, thick white rim, breathing halo
  dot: () => '<span class="halo"></span><span class="me-spot"></span>',
  // the old light-blue pin, kept to compare
  classic: () => RINGS + GROUND + '<svg class="pin" viewBox="0 0 30 40"><path d="M15 38.5C15 38.5 3 24.6 3 15a12 12 0 0 1 24 0c0 9.6-12 23.5-12 23.5Z" fill="#4fb3ff" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/><circle cx="15" cy="15" r="5" fill="#fff"/></svg>',
}
