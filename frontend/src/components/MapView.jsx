import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useConfig } from '../config/store'
import { WARSAW_CENTER } from '../data/api'
import { categoryMatchExpr } from '../data/categories'
import { closedNow, enabledPinGroups, PIN_GROUPS, pinGroup, withPinGroups } from '../data/pinGroups'
import { ME_STYLES } from './meMarker'
import { CITY_CLICK_LAYERS, ensureCityLayers, highlightWalk, setCityData, setCityVisibility } from './cityLayers'

const PIN_PARAMS = PIN_GROUPS.map((g) => g.param)
import { translate, useLang } from '../i18n'
import { applyMapDesign, firstSymbolLayer, styleFor } from './mapStyle'

const SRC = 'wl-features', BOUNDARY = 'wl-boundary', AREAS = 'wl-busyareas', ROUTE = 'wl-route'
const AREA_LABEL = 'wl-busyareas-label'
const AREA_FILL_OPACITY = ['interpolate', ['linear'], ['zoom'], 11, 0.5, 16, 0.36]
const FADE = { duration: 900, delay: 0 }
// what fades out on the start page and back in when the map is entered: [layer, paint property, shown value]
const REVEAL = [
  ['wl-dots', 'circle-stroke-opacity', 1], ['wl-glow', 'circle-opacity', 0.55], ['wl-starred', 'circle-stroke-opacity', 1],
  ['wl-busyareas-fill', 'fill-opacity', AREA_FILL_OPACITY], ['wl-busyareas-line', 'line-opacity', 1], ['wl-busyareas-label', 'text-opacity', 1],
  ['wl-route', 'line-opacity', 1], ['wl-route-casing', 'line-opacity', 0.9],
]
const AREA_LAYERS = ['wl-busyareas-fill', 'wl-busyareas-line', AREA_LABEL]

/**
 * The busy areas are on by default, so one label explains them: "Tu się dzieje" / "Busy Area", once,
 * in the middle of the busiest area (features come sorted busiest first).
 */
function busiestAreaLabel(fc) {
  const area = (fc?.features || []).find((f) => f.properties.level === 'busy' && f.geometry?.type === 'Polygon')
  if (!area) return EMPTY
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: interiorPoint(area.geometry.coordinates) } }] }
}

/** The point inside a polygon furthest from its edges (grid search, then refine): its visual middle. */
function interiorPoint(rings) {
  const k = Math.cos((rings[0][0][1] * Math.PI) / 180) // squash longitude so distances are roughly metric
  const P = rings.map((r) => r.map(([x, y]) => [x * k, y]))
  const inside = (x, y) => P.reduce((acc, r, ri) => {
    let c = false
    for (let i = 0, j = r.length - 1; i < r.length; j = i++) if ((r[i][1] > y) !== (r[j][1] > y) && x < r[j][0] + ((y - r[j][1]) * (r[i][0] - r[j][0])) / (r[i][1] - r[j][1])) c = !c
    return ri === 0 ? c : acc && !c
  }, false)
  const clearance = (x, y) => {
    let best = Infinity
    for (const r of P) for (let i = 1; i < r.length; i++) {
      const [ax, ay] = r[i - 1], [bx, by] = r[i], dx = bx - ax, dy = by - ay
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1e-12)))
      best = Math.min(best, Math.hypot(x - ax - t * dx, y - ay - t * dy))
    }
    return best
  }
  const xs = P[0].map((p) => p[0]), ys = P[0].map((p) => p[1])
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))
  let bx = (Math.min(...xs) + Math.max(...xs)) / 2, by = (Math.min(...ys) + Math.max(...ys)) / 2, bestC = -1
  for (const [range, n] of [[span / 2, 24], [span / 24, 12]]) {
    const cx = bx, cy = by
    for (let i = 0; i <= n; i++) for (let j = 0; j <= n; j++) {
      const x = cx - range + (2 * range * i) / n, y = cy - range + (2 * range * j) / n
      if (!inside(x, y)) continue
      const c = clearance(x, y)
      if (c > bestC) { bestC = c; bx = x; by = y }
    }
  }
  return [bx / k, by]
}

/** Half the size of the map's own "Warsaw" label (the capital-city layer of whichever base style is on). */
function halfCityLabelSize(m) {
  const symbols = (m.getStyle().layers || []).filter((l) => l.type === 'symbol')
  const city = symbols.find((l) => /capital/.test(l.id) && /city|place|label/.test(l.id)) || symbols.find((l) => /city/.test(l.id))
  const size = city && m.getLayoutProperty(city.id, 'text-size')
  if (typeof size === 'number') return size / 2
  if (Array.isArray(size) && size[0] === 'interpolate') return [...size.slice(0, 3), ...size.slice(3).map((v, i) => (i % 2 && typeof v === 'number' ? v / 2 : v))]
  if (size?.stops) return { ...size, stops: size.stops.map(([z, v]) => [z, v / 2]) }
  return 10
}

const HOME_SHARE = 0.8 // the home view shows this share of all pins
const HOME_ZOOM = [11, 15] // never further out / closer in than this, whatever the data

/**
 * Home view padding: keep the view clear of the search bar (top) and toolbar (bottom), and use the same
 * amount top and bottom so the centre point lands in the middle of the screen.
 */
function homePadding() {
  const gap = 12
  const top = (document.querySelector('.top-left')?.getBoundingClientRect().bottom ?? 90) + gap
  const bottom = window.innerHeight - (document.querySelector('.toolbar')?.getBoundingClientRect().top ?? window.innerHeight - 80) + gap
  const v = Math.max(top, bottom)
  return { top: v, bottom: v, left: 24, right: 24 }
}

/**
 * Home view: always centred on Rondo Dmowskiego, zoomed in as far as possible while HOME_SHARE of the
 * visible pins (current filters: pitches are hidden by default, time window, …) stay on screen. For each pin, the deepest zoom at which it still fits inside the free area (screen
 * minus padding) is log2(halfSize / offset), where offset is its mercator distance from the centre in
 * zoom-0 pixels. The home zoom is the (1 − HOME_SHARE) quantile of those: 80% of pins fit at it or deeper.
 */
function homeView(m, features) {
  const pad = homePadding()
  const el = m.getContainer()
  const halfW = (el.clientWidth - pad.left - pad.right) / 2
  const halfH = (el.clientHeight - pad.top - pad.bottom) / 2
  const c = maplibregl.MercatorCoordinate.fromLngLat(WARSAW_CENTER)
  const zooms = []
  for (const f of features || []) {
    const [lng, lat] = f.geometry?.coordinates || []
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    const p = maplibregl.MercatorCoordinate.fromLngLat([lng, lat])
    const dx = Math.abs(p.x - c.x) * 512, dy = Math.abs(p.y - c.y) * 512 // world is 512 px wide at zoom 0
    const z = Math.log2(Math.min(dx ? halfW / dx : Infinity, dy ? halfH / dy : Infinity))
    if (Number.isFinite(z)) zooms.push(z) // a hidden / zero-size container would otherwise yield NaN
  }
  zooms.sort((a, b) => a - b)
  const z = zooms.length ? zooms[Math.floor((1 - HOME_SHARE) * (zooms.length - 1))] : 12.5
  const zoom = Math.min(HOME_ZOOM[1], Math.max(HOME_ZOOM[0], Number.isFinite(z) ? z : 12.5))
  return { center: WARSAW_CENTER, zoom, pitch: 0, bearing: 0 }
}

const EMPTY = { type: 'FeatureCollection', features: [] }
const LAYERS = ['wl-glow', 'wl-dots', 'wl-starred', 'wl-selected']

function timeRange(window) {
  const now = new Date()
  const iso = (d) => d.toISOString().slice(0, 16)
  const end = new Date(now)
  const start = new Date(now); start.setHours(now.getHours() - 2)
  if (window === 'today') end.setHours(23, 59)
  else if (window === 'weekend') {
    const day = now.getDay() // 0 Sun .. 6 Sat
    const toSat = day === 0 ? -1 : (6 - day)
    start.setDate(now.getDate() + Math.max(0, toSat)); if (toSat > 0) start.setHours(0, 0)
    end.setDate(now.getDate() + (day === 0 ? 0 : toSat + 1)); end.setHours(23, 59)
  }
  else if (window === 'week') end.setDate(now.getDate() + 7)
  else if (window === 'month') end.setDate(now.getDate() + 30)
  else return null
  return [iso(start), iso(end)]
}

// Public invitations and everything users create themselves ("+ Create event" pins carry an `audience`)
const IS_INVITE = ['any', ['to-boolean', ['get', 'is_public_invite']], ['has', 'audience']]

function buildFilter(v, favourites, favOnly) {
  const kinds = []
  const parts = ['any']
  if (v.showEvents) parts.push(['all', ['in', ['get', 'kind'], ['literal', ['event', 'class']]], ['!', IS_INVITE]]) // classes are dated too
  if (v.showInvites) parts.push(IS_INVITE)
  if (v.showPlaces) parts.push(['all', ['==', ['get', 'kind'], 'place'], ['!=', ['get', 'venue_type'], 'pitch']])
  if (v.showPitches) parts.push(['==', ['get', 'venue_type'], 'pitch'])
  if (parts.length === 1) parts.push(false)
  const f = ['all', parts, ['in', ['get', 'pin_group'], ['literal', enabledPinGroups(v)]]] // toolbar pin options
  const range = timeRange(v.timeWindow)
  if (range) f.push(['any', ['!', ['has', 'starts_at']], ['all', ['>=', ['get', 'starts_at'], range[0]], ['<=', ['get', 'starts_at'], range[1]]]])
  if (favOnly) f.push(['in', ['get', 'event_id'], ['literal', [...favourites]]])
  if (v.openNow) f.push(['!', ['to-boolean', ['get', 'closed_now']]]) // pin box "Open now" (pinGroups.closedNow)
  void kinds
  return f
}

/** How many pins each toolbar option holds under the current settings (time window etc.), all options on. */
export function countPinGroups(features, v, favourites, favOnly) {
  const counts = Object.fromEntries(PIN_GROUPS.map((g) => [g.id, 0]))
  for (const f of visiblePins(features, v, favourites, favOnly, { allGroups: true })) counts[pinGroup(f.properties)]++
  return counts
}

/** JS twin of buildFilter(): the pins actually drawn with the current settings (keep the two in sync). */
function visiblePins(features, v, favourites, favOnly, { allGroups = false } = {}) {
  const groups = new Set(allGroups ? PIN_GROUPS.map((g) => g.id) : enabledPinGroups(v))
  const range = timeRange(v.timeWindow)
  const favs = new Set(favourites)
  return (features || []).filter(({ properties: p }) => {
    const invite = Boolean(p.is_public_invite || p.audience)
    const shown = (v.showEvents && (p.kind === 'event' || p.kind === 'class') && !invite) || (v.showInvites && invite)
      || (v.showPlaces && p.kind === 'place' && p.venue_type !== 'pitch') || (v.showPitches && p.venue_type === 'pitch')
    if (!shown || !groups.has(pinGroup(p))) return false
    if (range && p.starts_at != null && !(p.starts_at >= range[0] && p.starts_at <= range[1])) return false
    if (v.openNow && closedNow(p)) return false
    return !favOnly || favs.has(p.event_id)
  })
}

export const MapView = forwardRef(function MapView({ features, busyAreas, route, me, favourites, favOnly, selectedId, onPick, onReady, onMove, revealed = true, draftPin, onDraftPin, city = {}, onPickWalk }, ref) {
  const { values } = useConfig()
  const { lang, t } = useLang()
  const el = useRef(null)
  const map = useRef(null)
  const vRef = useRef(values)
  vRef.current = values
  // latest props for handlers registered once (style.load fires again after every setStyle)
  const dataRef = useRef({ features, favourites, favOnly, busyAreas, route })
  dataRef.current = { features, favourites, favOnly, busyAreas, route }
  const meMarker = useRef(null)
  const draftMarker = useRef(null)
  const draftRef = useRef({ draftPin, onDraftPin })
  draftRef.current = { draftPin, onDraftPin }
  const cityRef = useRef({ city, onPickWalk }) // toilets / AED / walking routes (cityLayers.js)
  cityRef.current = { city, onPickWalk }
  const userMoved = useRef(false), homed = useRef(false)
  const revealedRef = useRef(revealed)

  const shownPins = () => { const d = dataRef.current; return visiblePins(d.features?.features, vRef.current, d.favourites, d.favOnly) }

  // open on the home view once the pins are in, unless the user already started moving the map
  function openOnHome(m) {
    const f = shownPins()
    if (homed.current || userMoved.current || !f.length) return
    const el = m.getContainer()
    if (!el.clientWidth || !el.clientHeight) return // not laid out yet; the resize handler will retry
    homed.current = true
    const view = homeView(m, f)
    // behind the start page sit a touch further out, so entering the map glides in instead of jumping
    m.jumpTo(revealedRef.current ? view : { ...view, zoom: view.zoom - 0.35 })
  }
  const styleKey = styleFor(values)

  useImperativeHandle(ref, () => ({
    zoomBy: (d) => map.current?.zoomTo(map.current.getZoom() + d, { duration: 350 }),
    home: () => map.current?.easeTo({ ...homeView(map.current, shownPins()), duration: 1200 }),
    flyTo: (f, zoom = 15) => map.current?.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.current.getZoom(), zoom), duration: 1100, essential: true,
      padding: window.innerWidth < 768 ? { bottom: window.innerHeight * 0.45 } : { right: 380 } }),
    getZoom: () => map.current?.getZoom(),
    getMap: () => map.current,
    center: () => map.current && map.current.getCenter().toArray(),
  }))

  // ---------- init ----------
  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current, style: styleKey, center: WARSAW_CENTER, zoom: 12, minZoom: 9.5, maxZoom: 19,
      maxBounds: [[20.4, 51.9], [21.8, 52.6]], attributionControl: { compact: true }, antialias: true, fadeDuration: 150,
    })
    map.current = m
    // map credits: the (i) starts closed on every load (MapLibre opens it on wide screens); tap it to read them
    const credits = m.getContainer().querySelector('.maplibregl-ctrl-attrib')
    credits?.querySelector('summary')?.addEventListener('click', () => { credits.dataset.touched = '1' }, { once: true })
    const closeCredits = () => { if (credits && !credits.dataset.touched) credits.classList.remove('maplibregl-compact-show') }
    closeCredits()
    m.on('styledata', closeCredits)
    m.on('load', () => { ensureLayers(m); applyMapDesign(m, vRef.current); openOnHome(m); onReady?.() })
    m.on('resize', () => openOnHome(m))
    // a drag / wheel / touch counts as the user moving the map; a window resize (also an originalEvent) doesn't
    m.on('movestart', (e) => { const t = e.originalEvent?.type; if (t && t !== 'resize') userMoved.current = true })
    m.on('style.load', () => { if (!m.getSource(SRC)) { ensureLayers(m); applyMapDesign(m, vRef.current) } })
    m.on('move', () => onMove?.(m.getZoom()))
    // while "+ Create event" is open a tap anywhere moves its pin instead of opening boxes
    m.on('click', (e) => { const d = draftRef.current; if (d.draftPin) d.onDraftPin?.(e.lngLat.toArray()) })
    m.on('click', 'wl-dots', (e) => { const f = e.features?.[0]; if (f && !draftRef.current.draftPin) onPick({ type: 'Feature', id: f.id, geometry: f.geometry, properties: parseProps(f.properties) }) })
    m.on('mouseenter', 'wl-dots', () => { m.getCanvas().style.cursor = 'pointer' })
    m.on('mouseleave', 'wl-dots', () => { m.getCanvas().style.cursor = '' })
    // toilets / AEDs open a box like any place; a walking route opens its own box (full line from the data)
    m.on('click', CITY_CLICK_LAYERS.amenity, (e) => { const f = e.features?.[0]; if (f && !draftRef.current.draftPin) onPick({ type: 'Feature', id: f.id, geometry: f.geometry, properties: parseProps(f.properties) }) })
    m.on('click', CITY_CLICK_LAYERS.walk, (e) => {
      const key = e.features?.[0]?.properties.walk_key
      if (!key || draftRef.current.draftPin || m.queryRenderedFeatures(e.point, { layers: ['wl-dots', CITY_CLICK_LAYERS.amenity].filter((l) => m.getLayer(l)) }).length) return
      const { city, onPickWalk } = cityRef.current
      const i = Number(key.split('-')[1])
      const route = city.walks?.features?.[i]
      if (route) onPickWalk?.({ ...route, properties: { ...route.properties, walk_key: key, color: e.features[0].properties.color } })
    })
    for (const id of Object.values(CITY_CLICK_LAYERS)) {
      m.on('mouseenter', id, () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', id, () => { m.getCanvas().style.cursor = '' })
    }
    return () => m.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function ensureLayers(m) {
    const d = dataRef.current
    if (!m.getSource(SRC)) m.addSource(SRC, { type: 'geojson', data: withPinGroups(d.features) || { type: 'FeatureCollection', features: [] }, promoteId: 'event_id' })
    if (!m.getSource(BOUNDARY)) m.addSource(BOUNDARY, { type: 'geojson', data: '/warsaw_boundary.geojson' })
    if (!m.getSource(AREAS)) m.addSource(AREAS, { type: 'geojson', data: d.busyAreas || EMPTY })
    if (!m.getSource(ROUTE)) m.addSource(ROUTE, { type: 'geojson', data: d.route || EMPTY })
    const before = firstSymbolLayer(m)
    // busy areas, Google "area busyness" style: pale yellow fill with a dotted golden outline (no labels).
    // Only the outer "busy" outline is drawn; the "very_busy" cores stay in the data.
    const outline = ['==', ['get', 'level'], 'busy']
    if (!m.getLayer('wl-busyareas-fill')) m.addLayer({ id: 'wl-busyareas-fill', type: 'fill', source: AREAS, filter: outline,
      paint: { 'fill-color': '#fcd462', 'fill-opacity': AREA_FILL_OPACITY } }, before)
    if (!m.getLayer('wl-busyareas-line')) m.addLayer({ id: 'wl-busyareas-line', type: 'line', source: AREAS, filter: outline, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#f0ac00', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.6, 16, 2.6], 'line-dasharray': [0.1, 2] } }, before)
    if (!m.getSource(AREA_LABEL)) m.addSource(AREA_LABEL, { type: 'geojson', data: busiestAreaLabel(d.busyAreas) })
    if (!m.getLayer(AREA_LABEL)) m.addLayer({ id: AREA_LABEL, type: 'symbol', source: AREA_LABEL,
      layout: { 'text-field': translate('Busy Area'), 'text-font': ['Noto Sans Bold'], 'text-size': halfCityLabelSize(m), 'text-allow-overlap': true, 'text-ignore-placement': true },
      paint: { 'text-color': '#a06c00', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 } })
    if (!m.getLayer('wl-boundary-line')) m.addLayer({ id: 'wl-boundary-line', type: 'line', source: BOUNDARY, paint: { 'line-color': '#e7392b', 'line-width': 1.5, 'line-dasharray': [3, 3], 'line-opacity': 0.55 } }, before)
    if (!m.getLayer('wl-route-casing')) m.addLayer({ id: 'wl-route-casing', type: 'line', source: ROUTE, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 } })
    if (!m.getLayer('wl-route')) m.addLayer({ id: 'wl-route', type: 'line', source: ROUTE, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': vRef.current.accent, 'line-width': 3.5 } })
    if (!m.getLayer('wl-glow')) m.addLayer({ id: 'wl-glow', type: 'circle', source: SRC, paint: { 'circle-blur': 1, 'circle-opacity': 0.55 } })
    if (!m.getLayer('wl-dots')) m.addLayer({ id: 'wl-dots', type: 'circle', source: SRC, paint: {} })
    if (!m.getLayer('wl-starred')) m.addLayer({ id: 'wl-starred', type: 'circle', source: SRC, paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#f2a900', 'circle-stroke-width': 3 } })
    if (!m.getLayer('wl-selected')) m.addLayer({ id: 'wl-selected', type: 'circle', source: SRC, filter: ['==', ['get', 'event_id'], '__none__'], paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3, 'circle-radius': 16 } })
    ensureCityLayers(m, cityRef.current.city, before, 'wl-glow')
    setCityVisibility(m, vRef.current)
    m.moveLayer(AREA_LABEL) // above the event dots, so it never hides
    styleMarkers(m, vRef.current)
    applyReveal(m, vRef.current, revealedRef.current)
    refreshFilters(m)
    styleRoute(m, vRef.current)
    for (const id of AREA_LAYERS) m.setLayoutProperty(id, 'visibility', vRef.current.busyAreas ? 'visible' : 'none')
    m.setLayoutProperty('wl-boundary-line', 'visibility', vRef.current.cityBoundary ? 'visible' : 'none')
    m.setPaintProperty('wl-boundary-line', 'line-color', vRef.current.accent)
  }

  // ---------- style switch (palette / dark) ----------
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    const m = map.current
    if (!m) return
    m.setStyle(styleKey, { diff: false }) // the init-time 'style.load' handler re-adds our sources/layers
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleKey])

  // ---------- data ----------
  useEffect(() => { const m = map.current; if (m?.getSource(SRC) && features) { m.getSource(SRC).setData(withPinGroups(features)); openOnHome(m) } }, [features])
  // "Open now": re-check opening hours every few minutes while it's on (places open and close as time passes)
  useEffect(() => {
    if (!values.openNow) return
    const id = setInterval(() => { const m = map.current; if (m?.getSource(SRC) && features) m.getSource(SRC).setData(withPinGroups(features)) }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [values.openNow, features])
  useEffect(() => {
    const m = map.current
    if (!m?.getSource(AREAS) || !busyAreas) return
    m.getSource(AREAS).setData(busyAreas)
    m.getSource(AREA_LABEL)?.setData(busiestAreaLabel(busyAreas))
  }, [busyAreas])
  useEffect(() => { const m = map.current; if (m?.getLayer(AREA_LABEL)) m.setLayoutProperty(AREA_LABEL, 'text-field', t('Busy Area')) }, [lang, t])
  // toilets / AED / walking routes: new data, toggles, and the route whose box is open
  useEffect(() => { const m = map.current; if (m?.getSource('wl-amenities')) setCityData(m, city) }, [city])
  useEffect(() => { const m = map.current; if (m) setCityVisibility(m, values) }, [values.showToilets, values.showAed, values.showWalks]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const m = map.current; if (m) highlightWalk(m, selectedId) }, [selectedId])
  useEffect(() => { const m = map.current; if (m?.getSource(ROUTE)) m.getSource(ROUTE).setData(route || EMPTY) }, [route])
  useEffect(() => { const m = map.current; if (!m?.getLayer('wl-busyareas-fill')) return; for (const id of AREA_LAYERS) m.setLayoutProperty(id, 'visibility', values.busyAreas ? 'visible' : 'none') }, [values.busyAreas])
  useEffect(() => { const m = map.current; if (m?.getLayer('wl-route')) styleRoute(m, values) }, [values.routeStyle, values.accent])

  // "+ Create event": a red draggable pin (same shape as "me") where the new event happens
  useEffect(() => {
    const m = map.current
    if (!m) return
    if (!draftPin) { draftMarker.current?.remove(); draftMarker.current = null; return }
    if (!draftMarker.current) {
      const el = document.createElement('div'); el.className = 'draft-marker'
      el.innerHTML = `<span class="draft-label">${t('Your event')}</span>`
        + '<svg class="pin" viewBox="0 0 30 40"><path d="M15 38.5C15 38.5 3 24.6 3 15a12 12 0 0 1 24 0c0 9.6-12 23.5-12 23.5Z" fill="var(--accent)" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/><path d="M15 10v10M10 15h10" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></svg>'
      draftMarker.current = new maplibregl.Marker({ element: el, draggable: true, anchor: 'bottom' }).setLngLat(draftPin).addTo(m)
      draftMarker.current.on('dragend', () => draftRef.current.onDraftPin?.(draftMarker.current.getLngLat().toArray()))
      if (!m.getBounds().contains(draftPin)) m.easeTo({ center: draftPin, duration: 600 })
    } else draftMarker.current.setLngLat(draftPin)
  }, [draftPin, t])

  // "me": the "you are here" marker, style picked in the editor (Map design -> My position marker).
  // HTML marker so CSS can animate it; rebuilt when the style or language changes.
  useEffect(() => {
    const m = map.current
    if (!m) return
    meMarker.current?.remove(); meMarker.current = null
    if (!me || !values.showMe) return
    const el = document.createElement('div')
    el.className = `me-marker me-${ME_STYLES[values.meStyle] ? values.meStyle : 'syrenka'}`
    el.innerHTML = ME_STYLES[values.meStyle] ? ME_STYLES[values.meStyle](t('You are here')) : ME_STYLES.syrenka()
    meMarker.current = new maplibregl.Marker({ element: el }).setLngLat(me).addTo(m)
  }, [me, values.showMe, values.meStyle, t])

  // ---------- design params ----------
  useEffect(() => {
    const m = map.current
    if (!m?.isStyleLoaded()) return
    applyMapDesign(m, values)
  }, [values.streetLabels, values.poiLabels, values.borders, values.buildings, values.waterTint, values.mapPalette, values.cityBoundary, values.landuse])

  useEffect(() => {
    const m = map.current
    if (!m?.getLayer('wl-boundary-line')) return
    m.setLayoutProperty('wl-boundary-line', 'visibility', values.cityBoundary ? 'visible' : 'none')
    m.setPaintProperty('wl-boundary-line', 'line-color', values.accent)
  }, [values.cityBoundary, values.accent])

  useEffect(() => { const m = map.current; if (m?.getLayer('wl-dots')) { styleMarkers(m, values); if (!revealedRef.current) applyReveal(m, values, false) } }, [values.markerStyle, values.markerSize, values.colorBy, values.accent])

  function refreshFilters(m) {
    if (!m?.getLayer('wl-dots')) return
    const { favourites, favOnly } = dataRef.current
    const f = buildFilter(vRef.current, favourites, favOnly)
    m.setFilter('wl-dots', f)
    m.setFilter('wl-glow', f)
    m.setFilter('wl-starred', ['all', f, ['in', ['get', 'event_id'], ['literal', [...favourites]]]])
    m.setLayoutProperty('wl-starred', 'visibility', vRef.current.starredDefault || favOnly ? 'visible' : 'none')
  }
  useEffect(() => { refreshFilters(map.current) }, [...PIN_PARAMS.map((k) => values[k]), values.showEvents, values.showPlaces, values.showPitches, values.showInvites, values.timeWindow, values.starredDefault, values.openNow, favourites, favOnly])

  // ---------- selected pulse ----------
  useEffect(() => {
    const m = map.current
    if (!m?.getLayer('wl-selected')) return
    m.setFilter('wl-selected', ['==', ['get', 'event_id'], selectedId ?? '__none__'])
    if (!selectedId) return
    let t0 = performance.now(), raf
    const tick = (t) => {
      const k = Math.min(1, Math.max(0, ((t - t0) / 1200) % 1)) // rAF timestamps can precede t0 by a frame
      if (m.getLayer('wl-selected')) {
        m.setPaintProperty('wl-selected', 'circle-radius', 10 + k * 22)
        m.setPaintProperty('wl-selected', 'circle-stroke-opacity', 1 - k)
        m.setPaintProperty('wl-selected', 'circle-stroke-color', values.accent)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [selectedId, values.accent])

  // start page <-> map: fade the pins, busy areas and route in or out (MapLibre paint transitions)
  useEffect(() => {
    revealedRef.current = revealed
    const m = map.current
    if (m?.getLayer('wl-dots')) applyReveal(m, values, revealed)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealed])

  return <div ref={el} className={`map ${revealed ? '' : 'quiet'}`} />
})

function applyReveal(m, v, on) {
  if (!m.getLayer('wl-dots')) return
  for (const [id, prop, shown] of REVEAL) {
    if (!m.getLayer(id)) continue
    m.setPaintProperty(id, `${prop}-transition`, FADE)
    m.setPaintProperty(id, prop, on ? shown : 0)
  }
  m.setPaintProperty('wl-dots', 'circle-opacity-transition', FADE)
  if (on) styleMarkers(m, v) // restores each marker style's own opacity
  else m.setPaintProperty('wl-dots', 'circle-opacity', 0)
}

function parseProps(p) {
  const out = { ...p }
  for (const k of ['categories', 'upcoming', 'opening_hours', 'equipment', 'host']) {
    if (typeof out[k] === 'string' && /^[[{]/.test(out[k])) { try { out[k] = JSON.parse(out[k]) } catch { /* keep */ } }
  }
  return out
}

function styleMarkers(m, v) {
  const s = v.markerSize
  const color = v.colorBy === 'category' ? categoryMatchExpr()
    : v.colorBy === 'kind' ? ['case', ['to-boolean', ['get', 'is_public_invite']], '#0fa37f', ['==', ['get', 'kind'], 'event'], v.accent, '#2b6be7']
    : v.accent
  const base = ['interpolate', ['linear'], ['zoom'], 10, 2.2 * s, 13, 5 * s, 16, 9 * s, 19, 14 * s]
  const bigger = (k) => ['interpolate', ['linear'], ['zoom'], 10, 2.2 * s * k, 13, 5 * s * k, 16, 9 * s * k, 19, 14 * s * k]
  const paint = {
    dot: { 'circle-radius': base, 'circle-color': color, 'circle-stroke-width': 0, 'circle-opacity': 0.95 },
    ring: { 'circle-radius': base, 'circle-color': 'rgba(255,255,255,0.15)', 'circle-stroke-color': color, 'circle-stroke-width': 2.2, 'circle-opacity': 1 },
    glow: { 'circle-radius': base, 'circle-color': color, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.2, 'circle-opacity': 1 },
    pin: { 'circle-radius': bigger(1.5), 'circle-color': color, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5, 'circle-opacity': 1 },
  }[v.markerStyle]
  for (const [k, val] of Object.entries(paint)) m.setPaintProperty('wl-dots', k, val)
  m.setPaintProperty('wl-glow', 'circle-color', color)
  m.setPaintProperty('wl-glow', 'circle-radius', bigger(2.6))
  m.setLayoutProperty('wl-glow', 'visibility', v.markerStyle === 'glow' ? 'visible' : 'none')
  m.setPaintProperty('wl-starred', 'circle-radius', bigger(1.7))
}

function styleRoute(m, v) {
  m.setPaintProperty('wl-route', 'line-color', v.accent)
  const dash = { dashed: [2, 1.6], solid: [1, 0], dots: [0.1, 1.8] }[v.routeStyle] || [2, 1.6]
  m.setPaintProperty('wl-route', 'line-dasharray', dash)
  m.setLayoutProperty('wl-route', 'line-cap', v.routeStyle === 'dots' ? 'round' : 'round')
}

