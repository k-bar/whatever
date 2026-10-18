/**
 * The social signal: what *you* said you're going to, and whom you asked to join. This is the
 * user-generated layer Syrenka Selects is built on: anything people act on rises to the top.
 *
 * Stored locally so it works before login; when logged in the same action is also sent to the API
 * (PUT attendance / POST join-request), which later feeds the attendees / wanting_company counts
 * every visitor sees.
 */
import { useSyncExternalStore } from 'react'
import { isLoggedIn, LoginRequired, removeAttendance, requestJoin, setAttendance } from './api'

const KEY = 'syrenka.social.v1'
let state = read()
const listeners = new Set()

function read() {
  try { return { going: {}, joined: {}, ...JSON.parse(localStorage.getItem(KEY) || '{}') } } catch { return { going: {}, joined: {} } }
}
function write(next) {
  state = next
  try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* private mode */ }
  listeners.forEach((fn) => fn())
}
const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }

export const getSocial = () => state
export const useSocial = () => useSyncExternalStore(subscribe, getSocial, getSocial)
export const isGoing = (id) => Boolean(state.going[id])
export const hasAsked = (id) => Boolean(state.joined[id])

/** "I'm going, come with me". Returns 'on' | 'off' (toggled) and whether the API accepted it. */
export async function toggleGoing(feature, { wantsCompany = true } = {}) {
  const p = feature.properties
  const id = String(p.event_id)
  const was = state.going[id]
  const on = !was
  // remember which date we said yes to: the pin may show another date of the same event by the time we say no
  const occ = on ? p.occurrence_id : was.occurrenceId ?? p.occurrence_id
  write({ ...state, going: on ? { ...state.going, [id]: { at: Date.now(), wantsCompany, title: p.title, occurrenceId: occ } } : omit(state.going, id) })
  let synced = false
  if (isLoggedIn() && occ) {
    try { await (on ? setAttendance(occ, wantsCompany) : removeAttendance(occ)); synced = true } catch (e) { if (!(e instanceof LoginRequired)) console.warn('attendance not saved', e) }
  }
  return { on, synced }
}

/** "Ask to join" the host of an invitation. Local mark always; API when logged in and we know whom to ask. */
export async function askToJoin(feature, message = null) {
  const p = feature.properties
  const id = String(p.event_id)
  if (state.joined[id]) return { on: true, synced: false, already: true }
  write({ ...state, joined: { ...state.joined, [id]: { at: Date.now(), title: p.title } } })
  let synced = false
  const target = p.host?.id ?? p.host_user_id
  if (isLoggedIn() && p.occurrence_id && target) {
    try { await requestJoin(p.occurrence_id, target, message); synced = true } catch (e) { if (!(e instanceof LoginRequired)) console.warn('join request not sent', e) }
  }
  return { on: true, synced, needsLogin: !isLoggedIn() }
}

function omit(obj, key) { const { [key]: _, ...rest } = obj; return rest }
