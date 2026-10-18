/**
 * Thin client for the python backend (FastAPI, backend/app). Real data only: when the API is
 * unreachable the map is empty and the badge says so.
 * API base: VITE_API_URL (default "/api", proxied by vite to http://localhost:8000).
 */
import { smartSearch } from '../search/engine'
import { getLang } from '../i18n'

const BASE = import.meta.env.VITE_API_URL || '/api'
export const WARSAW_BBOX = [20.85, 52.1, 21.27, 52.37]
// Our declared centre point: Rondo Romana Dmowskiego (Marszałkowska × Aleje Jerozolimskie).
export const WARSAW_CENTER = [21.0114, 52.2306]

/** Events mode shows only these: a real event (not a place or a regular class) with a date. */
export const isDatedEvent = (p) => p.kind === 'event' && Boolean(p.starts_at)

export const dataStatus = { source: 'loading' } // 'api' | 'offline' | 'loading'

async function get(path, opts = {}) {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), opts.timeout ?? 2500)
  try {
    const r = await fetch(`${BASE}${path}`, { signal: ctl.signal, ...opts })
    if (!r.ok) {
      const body = await r.json().catch(() => null)
      const detail = Array.isArray(body?.detail) ? body.detail.map((d) => d.msg).join(', ') : body?.detail
      throw Object.assign(new Error(detail || String(r.status)), { status: r.status })
    }
    if (r.status === 204) return null
    return await r.json()
  } finally {
    clearTimeout(t)
  }
}

/**
 * Image links. Paths the API serves itself (user event photos) come back as "/userevents/…": point them
 * at the API. Outside links are asked for over https: the city's posters come as http://um.warszawa.pl/…
 * and the site is https, so they're "mixed content" — Chrome quietly upgrades those, Safari blocks them
 * (posters showed in Chrome only). Their server answers on https.
 */
export const assetUrl = (url) => (url?.startsWith('/') ? `${BASE}${url}` : url?.replace(/^http:\/\//i, 'https://'))
const withImage = (o) => (o?.image_url ? { ...o, image_url: assetUrl(o.image_url) } : o)
// the pin's own picture, and the posters of a place's upcoming events (the box's "Upcoming here" strip)
const withAssets = (f) => ({ ...f, properties: { ...withImage(f.properties), ...(Array.isArray(f.properties.upcoming) && { upcoming: f.properties.upcoming.map(withImage) }) } })

export async function fetchFeatures() {
  try {
    // ?lang: titles and descriptions in the UI language (translated on the server, originals kept).
    // Events and recurring classes are asked for separately: the API caps each list at 2000, and daily
    // classes alone would otherwise fill it and push real events out of the month.
    const q = `bbox=${WARSAW_BBOX.join(',')}&limit=2000&lang=${getLang()}`
    const [events, classes, places, mine] = await Promise.all([
      get(`/events?${q}&kind=event`, { timeout: 15000 }),
      get(`/events?${q}&kind=class`, { timeout: 15000 }).catch(() => ({ features: [] })),
      get(`/places?bbox=${WARSAW_BBOX.join(',')}&lang=${getLang()}`, { timeout: 15000 }),
      fetchPrivateUserEvents(),
    ])
    dataStatus.source = 'api'
    return { type: 'FeatureCollection', features: [...events.features, ...classes.features, ...places.features, ...mine].map(withAssets) }
  } catch {
    dataStatus.source = 'offline'
    return { type: 'FeatureCollection', features: [] }
  }
}

/**
 * "In the city" layers (Warsaw open data, see components/cityLayers.js): 'toilets' and 'aed' come from
 * GET /places?category=…, 'walks' (tourist walking routes) from GET /routes. Empty when the API lacks them.
 */
export async function fetchCityLayer(id) {
  try {
    return await get(id === 'walks' ? '/routes' : `/places?category=${id}`, { timeout: 15000 })
  } catch {
    return { type: 'FeatureCollection', features: [] }
  }
}

export async function fetchSources() {
  try {
    return await get('/sources')
  } catch {
    return []
  }
}

/* ---------- past events: stored, never searched ---------- */

const toDate = (iso) => new Date(String(iso).replace(/([+-]\d{2})$/, '$1:00'))
/** An event is past once it has ended (or started, when it has no end). Undated places never are. */
export const isPast = (p, now = Date.now()) => !!p?.starts_at && toDate(p.ends_at || p.starts_at).getTime() < now
/** Search shows only upcoming and ongoing things; past events stay stored (backend keeps them as history). */
export const upcoming = (features) => (features || []).filter((f) => !isPast(f.properties))

/**
 * Search. mode ∈ search | events | assistant. The backend has no search endpoint, so this
 * filters the already-loaded features client-side.
 */
export async function runSearch(mode, q, features, opts = {}) {
  return localSearch(mode, q, upcoming(features), opts)
}

/** Search over the loaded pins: src/search/engine.js reads what / when / where and ranks with tolerances. */
async function localSearch(mode, q, features, opts = {}) {
  const r = await smartSearch(q, features, { mode, category: opts.category, when: opts.when, where: opts.where })
  if (mode !== 'assistant') return r
  const n = r.results.length
  const top = r.results.slice(0, 3).map((f) => `• ${f.properties.title}${f.properties.venue_name ? ` @ ${f.properties.venue_name}` : ''}`).join('\n')
  const answer = n
    ? `${r.exact ? `${r.exact} exact match${r.exact === 1 ? '' : 'es'}` : 'No exact matches, but close ones'} for “${r.summary}”. My top picks:\n${top}\n\nTap one to open it on the map.`
    : `Nothing matches “${q}” yet. Try a district (Praga, Mokotów), a day (Saturday, weekend), a mood (jazz, run, picnic) or a venue.`
  return { ...r, answer }
}

/* ---------- position, routing, busy areas ---------- */

// Free, keyless, CORS-enabled IP geolocation services, tried in order (ipapi.co rate-limits quickly).
const IP_PROVIDERS = [
  ['https://get.geojs.io/v1/ip/geo.json', (j) => ({ lat: +j.latitude, lng: +j.longitude, city: j.city })],
  ['https://ipwho.is/', (j) => (j.success === false ? null : { lat: +j.latitude, lng: +j.longitude, city: j.city })],
  ['https://ipapi.co/json/', (j) => (j.error ? null : { lat: +j.latitude, lng: +j.longitude, city: j.city })],
]
const inWarsawArea = ({ lat, lng }) => Math.abs(lat - 52.23) < 0.6 && Math.abs(lng - 21.01) < 0.8

/**
 * Where am I? IP geolocation (no permission prompt, ~1–5 km accurate). Tries each provider until
 * one answers. Outside the Warsaw area (or all lookups failing) the user is placed at Centrum.
 */
export async function locateByIp() {
  for (const [url, parse] of IP_PROVIDERS) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(3000) })
      if (!r.ok) continue
      const pos = parse(await r.json())
      if (!pos || !Number.isFinite(pos.lat) || !Number.isFinite(pos.lng)) continue
      if (inWarsawArea(pos)) return { lngLat: [pos.lng, pos.lat], label: pos.city || 'Warsaw', exact: false, source: new URL(url).host }
      return { lngLat: WARSAW_CENTER, label: `${pos.city || 'outside Warsaw'} → shown at Centrum`, exact: false, source: new URL(url).host }
    } catch { /* try the next provider */ }
  }
  return { lngLat: WARSAW_CENTER, label: 'Centrum (IP lookup failed)', exact: false, source: null }
}

/* ---------- starting point (Profile → Set my location to) ---------- */

const START_KEY = 'warszawa-live.start.v1'

/** The starting point the user picked. When set it replaces the IP guess everywhere. */
export function loadStartPoint() {
  try { const s = JSON.parse(localStorage.getItem(START_KEY)); return Array.isArray(s?.lngLat) ? s : null } catch { return null }
}
export function saveStartPoint(point) {
  try { point ? localStorage.setItem(START_KEY, JSON.stringify(point)) : localStorage.removeItem(START_KEY) } catch { /* private mode */ }
}

const PHOTON = 'https://photon.komoot.io'
const photonPoint = (f) => {
  const p = f.properties
  const name = p.osm_value === 'postcode' ? p.name
    : p.housenumber ? `${p.street || p.name} ${p.housenumber}` : (p.name || p.street)
  const area = [p.osm_value !== 'postcode' && p.postcode, p.district || p.locality, p.city].filter(Boolean).join(', ')
  return { lngLat: f.geometry.coordinates, label: name || area || 'Warsaw', sub: area }
}

/** Address / postcode search for the starting point: Photon (OSM geocoder, keyless, CORS), Warsaw area only. */
export async function searchAddress(q, { signal } = {}) {
  const [w, s, e, n] = WARSAW_BBOX
  // lang=default: local (Polish) names; extra results leave room after dropping transit stops
  const r = await fetch(`${PHOTON}/api/?q=${encodeURIComponent(q)}&bbox=${w},${s - 0.01},${e + 0.01},${n}&limit=12&lang=default`, { signal })
  const isStop = (p) => p.osm_key === 'public_transport' || ['bus_stop', 'tram_stop', 'platform', 'stop_position'].includes(p.osm_value)
  const wantsNumber = /\d/.test(q) && !/^\s*\d{2}-?\d{3}\s*$/.test(q) // "Marszałkowska 10", not a postcode
  const seen = new Set()
  return ((await r.json()).features || [])
    .filter((f) => !isStop(f.properties))
    .sort((a, b) => (wantsNumber ? !!b.properties.housenumber - !!a.properties.housenumber : 0))
    .map(photonPoint)
    .filter((p) => !seen.has(p.label + p.sub) && seen.add(p.label + p.sub))
    .slice(0, 7)
}

/** Precise position from the device (asks for permission), labelled with the nearest address. */
export async function locateByDevice() {
  const pos = await new Promise((ok, fail) => navigator.geolocation
    ? navigator.geolocation.getCurrentPosition(ok, fail, { enableHighAccuracy: true, timeout: 10000 })
    : fail(new Error('no geolocation')))
  const lngLat = [pos.coords.longitude, pos.coords.latitude]
  try {
    const r = await fetch(`${PHOTON}/reverse?lon=${lngLat[0]}&lat=${lngLat[1]}&lang=default`, { signal: AbortSignal.timeout(4000) })
    const f = (await r.json()).features?.[0]
    if (f) return { ...photonPoint(f), lngLat }
  } catch { /* label falls back below */ }
  return { lngLat, label: 'My device location', sub: '' }
}

const WALK_KMH = 4.8, BIKE_KMH = 15

/** Street route from → to. Public OSRM demo; walking/cycling times derived from the distance. */
export async function routeTo(from, to) {
  const url = `https://router.project-osrm.org/route/v1/foot/${from[0]},${from[1]};${to[0]},${to[1]}?overview=full&geometries=geojson`
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(6000) })
    const j = await r.json()
    const route = j.routes?.[0]
    if (!route) throw new Error('no route')
    const km = route.distance / 1000
    return { geometry: route.geometry, km, walkMin: Math.round((km / WALK_KMH) * 60), bikeMin: Math.round((km / BIKE_KMH) * 60), source: 'osrm' }
  } catch {
    const km = haversineKm(from, to) * 1.3 // street factor
    return { geometry: { type: 'LineString', coordinates: [from, to] }, km, walkMin: Math.round((km / WALK_KMH) * 60), bikeMin: Math.round((km / BIKE_KMH) * 60), source: 'estimate' }
  }
}

export function haversineKm([lng1, lat1], [lng2, lat2]) {
  const R = 6371, toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

/**
 * Busy areas: detailed golden outlines of where people bump into each other (level "busy" and its
 * "very_busy" core). Built from OpenStreetMap by backend/scripts/build_busy_areas.py; served by GET /busyareas.
 */
export async function fetchBusyAreas() {
  try {
    return await get('/busyareas', { timeout: 8000 })
  } catch {
    return { type: 'FeatureCollection', features: [] }
  }
}

/**
 * Weather (16 city stations) and air quality (141 sensors), refreshed by the backend every 10 minutes:
 * GET /conditions -> { weather: FeatureCollection, air: FeatureCollection }. Null when the API is down.
 */
export async function fetchConditions() {
  try {
    return await get('/conditions', { timeout: 8000 })
  } catch {
    return null
  }
}

/* ---------- login + user events (backend/app/userevents) ---------- */

const TOKEN_KEY = 'syrenka.token.v1'
const AUTH_EVENT = 'syrenka:auth' // fired on window whenever someone logs in or out
const readToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
function writeToken(token) {
  try { if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
  window.dispatchEvent(new Event(AUTH_EVENT))
}

export const isLoggedIn = () => Boolean(readToken())
/** Subscribe to log in / log out. Returns the unsubscribe function. */
export const onAuthChange = (fn) => { window.addEventListener(AUTH_EVENT, fn); return () => window.removeEventListener(AUTH_EVENT, fn) }
export const logout = () => writeToken(null)

/** Thrown when an action needs an account: the UI shows "Log in" and the login form. */
export class LoginRequired extends Error {
  constructor() { super('Log in to continue'); this.status = 401; this.loginRequired = true }
}

/** POST /auth/login. Errors carry the API's message ("Wrong email or password"). */
export async function login(email, password) {
  const r = await get('/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email, password }), timeout: 10000 })
  writeToken(r.access_token)
}

/** POST /auth/register: a new account, logged in straight away. A confirmation link is mailed to `email`. */
export async function register(display_name, email, password) {
  const r = await get('/auth/register', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ display_name, email, password }), timeout: 10000 })
  writeToken(r.access_token)
}

const post = (path, body) => get(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), timeout: 10000 })

/** The link in the confirmation mail (?verify=…). Works logged out too. */
export async function verifyEmail(token) {
  const me = await post('/auth/verify', { token })
  window.dispatchEvent(new Event(AUTH_EVENT)) // email_verified changed for everyone showing "confirm your email"
  return me
}
export const resendVerification = () => authed('/auth/verify/resend', { method: 'POST' })
/** Mails a reset link; answers the same whether or not the address has an account. */
export const forgotPassword = (email) => post('/auth/password/forgot', { email })
/** From the reset mail (?reset=…): new password, every other session ends, this browser is logged in. */
export async function resetPassword(token, password) {
  writeToken((await post('/auth/password/reset', { token, password })).access_token)
}
/** Needs the current password; other devices are logged out, this one gets a fresh token. */
export async function changePassword(current_password, new_password) {
  writeToken((await authed('/me/password', { method: 'POST', body: { current_password, new_password } })).access_token)
}
export async function changeEmail(email, password) {
  const me = await authed('/me/email', { method: 'POST', body: { email, password } })
  window.dispatchEvent(new Event(AUTH_EVENT))
  return me
}
export async function logoutEverywhere() {
  writeToken((await authed('/auth/logout-all', { method: 'POST' })).access_token)
}

/** A call made as the logged-in user. No token, or an expired one, throws LoginRequired. */
async function authed(path, { body, ...opts } = {}) {
  const token = readToken()
  if (!token) throw new LoginRequired()
  try {
    return await get(path, {
      timeout: 15000, ...opts,
      headers: { authorization: `Bearer ${token}`, ...(body !== undefined && { 'content-type': 'application/json' }) },
      ...(body !== undefined && { body: JSON.stringify(body) }),
    })
  } catch (e) {
    if (e.status === 401) { writeToken(null); throw new LoginRequired() }
    if (e.status === 403 && e.message === 'Confirm your email first') e.verifyRequired = true
    throw e
  }
}

/** The current login token, for the chat socket (data/chat.js). */
export const sessionToken = readToken
export const authedCall = (path, opts) => authed(path, opts)
export const apiBase = BASE

/** My profile (GET /me) from PostgreSQL. Only when this browser already has a session: looking never creates an account. */
export async function fetchMe() {
  if (!readToken()) return null
  try { return await authed('/me', { timeout: 6000 }) } catch { return null }
}

/** Join requests to me that are still waiting for an answer (GET /me/join-requests). */
export async function fetchJoinRequests() {
  if (!readToken()) return []
  try { return await authed('/me/join-requests?direction=incoming&status=pending', { timeout: 6000 }) } catch { return [] }
}

/** My favourited events/venues saved with the account (GET /me/favourites); null when this browser has no session. */
export async function fetchFavourites() {
  if (!readToken()) return null
  try { return (await authed('/me/favourites', { timeout: 6000 })).ids } catch { return null }
}

/** Save the whole list of favourited events/venues (PUT /me/favourites). Logged in only; logged out, stars stay in the browser. */
export async function saveFavourites(ids) {
  try { return (await authed('/me/favourites', { method: 'PUT', body: { ids } })).ids } catch { return null }
}

/* ---------- profiles & friends (backend/app/routers/profiles.py) ---------- */

/** Call as the logged-in user when there is a session, anonymously otherwise (public profile pages). */
const maybeAuthed = (path, opts = {}) => (readToken() ? authed(path, opts) : get(path, { timeout: 8000, ...opts }))

/** A profile page: by id, or by @username. Includes stats and how the viewer relates to them. */
export const fetchProfile = (who) => maybeAuthed(typeof who === 'number' ? `/users/${who}/profile` : `/profiles/${encodeURIComponent(who)}`)
/** scope: going | been | hosting. Yourself and friends only (403 otherwise). */
export const fetchProfileEvents = (userId, scope) => maybeAuthed(`/users/${userId}/events?scope=${scope}`)
export const fetchFriends = (userId) => maybeAuthed(`/users/${userId}/friends`)
export const fetchFriendRequests = (direction = 'incoming') => authed(`/me/friend-requests?direction=${direction}`)
export const sendFriendRequest = (username) => authed('/friends/requests', { method: 'POST', body: { username } })
export const answerFriendRequest = (id, status) => authed(`/friend-requests/${id}`, { method: 'PATCH', body: { status } })
export const unfriend = (userId) => authed(`/friends/${userId}`, { method: 'DELETE' })
export const searchPeople = (q) => maybeAuthed(`/people/search?q=${encodeURIComponent(q)}`)
export const checkUsername = (name) => maybeAuthed(`/usernames/${encodeURIComponent(name)}/available`)
/** PATCH /me: display_name, username, gender ('f' | 'm' | '' to clear), bio, interests, hangouts. */
export const updateMe = (patch) => authed('/me', { method: 'PATCH', body: patch })
/** Upload a profile picture (shrunk in the browser, stored by the API); returns its path for photos[0]. */
export async function uploadProfilePhoto(file) {
  const r = await authed('/userevents/photos', { method: 'POST', body: { data_url: await shrinkPhoto(file, 800) } })
  return r.url
}

/** Shrink a photo in the browser (longest side 1600 px, JPEG) so uploads stay small. */
async function shrinkPhoto(file, max = 1600) {
  const img = await createImageBitmap(file)
  const k = Math.min(1, max / Math.max(img.width, img.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(img.width * k); canvas.height = Math.round(img.height * k)
  canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.85)
}

/**
 * "+ Create event": upload the photo (if any), then create. Public audiences land on the Syrenka Users API
 * (so they're in everyone's GET /events); the returned feature goes straight onto this map.
 */
export async function createUserEvent(values, photoFile) {
  try {
    let photo_id = null
    if (photoFile) photo_id = (await authed('/userevents/photos', { method: 'POST', body: { data_url: await shrinkPhoto(photoFile) } })).id
    const r = await authed('/userevents', { method: 'POST', body: { ...values, photo_id } })
    return { event: r.event, feature: withAssets(r.feature) }
  } catch (e) {
    // a 404 here means the API we talk to is older than backend/app/userevents
    if (e.status === 404) throw Object.assign(new Error('This server cannot create events yet (its API is not updated).'), { status: 404 })
    throw e
  }
}

/** Friends-only / invitation-only events I can see. Only asked for once this browser has a session. */
async function fetchPrivateUserEvents() {
  if (!readToken()) return []
  try {
    return (await authed('/userevents/private', { timeout: 8000 })).features
  } catch {
    return []
  }
}

/* ---------- going / asking to join (backend/app/routers/social.py) ---------- */

/** PUT /occurrences/{id}/attendance — "I'm going"; wants_company puts you on the "come with me" list. */
export async function setAttendance(occurrenceId, wantsCompany = true) {
  return authed(`/occurrences/${occurrenceId}/attendance`, { method: 'PUT', body: { wants_company: wantsCompany }, timeout: 8000 })
}

/** GET /occurrences/{id}/attendees — who's going (logged-in users only; [] otherwise). */
export async function fetchAttendees(occurrenceId) {
  if (!occurrenceId || !isLoggedIn()) return []
  try { return await authed(`/occurrences/${occurrenceId}/attendees`, { timeout: 8000 }) } catch { return [] }
}

/** POST /occurrences/{id}/join-requests — ask the host (or someone who wants company) to join them. */
export async function requestJoin(occurrenceId, targetUserId, message = null) {
  return authed(`/occurrences/${occurrenceId}/join-requests`, { method: 'POST', body: { target_user_id: targetUserId, message }, timeout: 8000 })
}

/* ---------- people on the map: "share my area" (backend/app/routers/people.py) ---------- */

/** Everyone sharing their area right now (rounded to ~100 m), with the open invitation they host next. */
export const fetchSharingPeople = () => maybeAuthed('/people/sharing')
export const fetchMyArea = () => authed('/me/area')
/** share: true needs where I am ([lng, lat]); false hides my pin at once. */
export const setMyArea = (share, lngLat) => authed('/me/area', { method: 'PUT', body: { share, ...(lngLat && { lng: lngLat[0], lat: lngLat[1] }) } })
