/**
 * Who am I: my account (GET /me), one store for every component that shows or needs it (the account
 * pill, the profile, create event, chats, friend events on the map). Loaded once, again on log in / out
 * (and when the email gets confirmed) and when I edit my profile. Only the newest answer counts.
 */
import { useSyncExternalStore } from 'react'
import { fetchMe, isLoggedIn, onAuthChange, onMeChange } from './api'

// me: undefined = loading, null = logged out, else GET /me. loggedIn follows the token straight away,
// so "Log in" turns into the pill before my name has arrived.
let state = { me: undefined, loggedIn: isLoggedIn() }
const listeners = new Set()
const emit = (patch) => { state = { ...state, ...patch }; listeners.forEach((fn) => fn()) }
export const subscribeMe = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }
export const getMe = () => state.me

export const useMe = () => useSyncExternalStore(subscribeMe, () => state.me)
export const useLoggedIn = () => useSyncExternalStore(subscribeMe, () => state.loggedIn)

let seq = 0
function refresh() {
  const n = ++seq
  const loggedIn = isLoggedIn()
  emit(loggedIn ? { loggedIn } : { loggedIn, me: null })
  fetchMe().then((me) => { if (n === seq) emit({ me }) })
}
refresh()
onAuthChange(refresh)
onMeChange(refresh) // new name / photo from Edit profile
