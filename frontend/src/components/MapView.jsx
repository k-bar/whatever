import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useConfig } from '../config/store'
import { WARSAW_CENTER } from '../data/api'
import { categoryMatchExpr } from '../data/categories'
import { applyMapDesign, firstSymbolLayer, styleFor } from './mapStyle'

const SRC = 'wl-features', BOUNDARY = 'wl-boundary', AREAS = 'wl-busyareas', ROUTE = 'wl-route'
const AREA_LAYERS = ['wl-busyareas-fill', 'wl-busyareas-line']

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
    zooms.push(Math.log2(Math.min(dx ? halfW / dx : Infinity, dy ? halfH / dy : Infinity)))
  }
  zooms.sort((a, b) => a - b)
  const z = zooms.length ? zooms[Math.floor((1 - HOME_SHARE) * (zooms.length - 1))] : 12.5
  return { center: WARSAW_CENTER, zoom: Math.min(HOME_ZOOM[1], Math.max(HOME_ZOOM[0], z)), pitch: 0, bearing: 0 }
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

function buildFilter(v, favourites, favOnly) {
  const kinds = []
  const parts = ['any']
  if (v.showEvents) parts.push(['all', ['==', ['get', 'kind'], 'event'], ['!', ['to-boolean', ['get', 'is_public_invite']]]])
  if (v.showInvites) parts.push(['to-boolean', ['get', 'is_public_invite']])
  if (v.showPlaces) parts.push(['all', ['==', ['get', 'kind'], 'place'], ['!=', ['get', 'venue_type'], 'pitch']])
  if (v.showPitches) parts.push(['==', ['get', 'venue_type'], 'pitch'])
  if (parts.length === 1) parts.push(false)
  const f = ['all', parts]
  const range = timeRange(v.timeWindow)
  if (range) f.push(['any', ['!', ['has', 'starts_at']], ['all', ['>=', ['get', 'starts_at'], range[0]], ['<=', ['get', 'starts_at'], range[1]]]])
  if (favOnly) f.push(['in', ['get', 'event_id'], ['literal', [...favourites]]])
  void kinds
  return f
}

/** JS twin of buildFilter(): the pins actually drawn with the current settings (keep the two in sync). */
function visiblePins(features, v, favourites, favOnly) {
  const range = timeRange(v.timeWindow)
  const favs = new Set(favourites)
  return (features || []).filter(({ properties: p }) => {
    const invite = Boolean(p.is_public_invite)
    const shown = (v.showEvents && p.kind === 'event' && !invite) || (v.showInvites && invite)
      || (v.showPlaces && p.kind === 'place' && p.venue_type !== 'pitch') || (v.showPitches && p.venue_type === 'pitch')
    if (!shown) return false
    if (range && p.starts_at != null && !(p.starts_at >= range[0] && p.starts_at <= range[1])) return false
    return !favOnly || favs.has(p.event_id)
  })
}

export const MapView = forwardRef(function MapView({ features, busyAreas, route, me, favourites, favOnly, selectedId, onPick, onReady, onMove }, ref) {
  const { values } = useConfig()
  const el = useRef(null)
  const map = useRef(null)
  const vRef = useRef(values)
  vRef.current = values
  // latest props for handlers registered once (style.load fires again after every setStyle)
  const dataRef = useRef({ features, favourites, favOnly, busyAreas, route })
  dataRef.current = { features, favourites, favOnly, busyAreas, route }
  const meMarker = useRef(null)
  const userMoved = useRef(false), homed = useRef(false)

  const shownPins = () => { const d = dataRef.current; return visiblePins(d.features?.features, vRef.current, d.favourites, d.favOnly) }

  // open on the home view once the pins are in, unless the user already started moving the map
  function openOnHome(m) {
    const f = shownPins()
    if (homed.current || userMoved.current || !f.length) return
    homed.current = true
    m.jumpTo(homeView(m, f))
  }
  const styleKey = styleFor(values)

  useImperativeHandle(ref, () => ({
    zoomBy: (d) => map.current?.zoomTo(map.current.getZoom() + d, { duration: 350 }),
    home: () => map.current?.easeTo({ ...homeView(map.current, shownPins()), duration: 1200 }),
    flyTo: (f, zoom = 15) => map.current?.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.current.getZoom(), zoom), duration: 1100, essential: true,
      padding: window.innerWidth < 768 ? { bottom: window.innerHeight * 0.45 } : { right: 380 } }),
    getZoom: () => map.current?.getZoom(),
    getMap: () => map.current,
  }))

  // ---------- init ----------
  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current, style: styleKey, center: WARSAW_CENTER, zoom: 12, minZoom: 9.5, maxZoom: 19,
      maxBounds: [[20.4, 51.9], [21.8, 52.6]], attributionControl: { compact: true }, antialias: true, fadeDuration: 150,
    })
    map.current = m
    m.on('load', () => { ensureLayers(m); applyMapDesign(m, vRef.current); openOnHome(m); onReady?.() })
    // a drag / wheel / touch counts as the user moving the map; a window resize (also an originalEvent) doesn't
    m.on('movestart', (e) => { const t = e.originalEvent?.type; if (t && t !== 'resize') userMoved.current = true })
    m.on('style.load', () => { if (!m.getSource(SRC)) { ensureLayers(m); applyMapDesign(m, vRef.current) } })
    m.on('move', () => onMove?.(m.getZoom()))
    m.on('click', 'wl-dots', (e) => { const f = e.features?.[0]; if (f) onPick({ type: 'Feature', id: f.id, geometry: f.geometry, properties: parseProps(f.properties) }) })
    m.on('mouseenter', 'wl-dots', () => { m.getCanvas().style.cursor = 'pointer' })
    m.on('mouseleave', 'wl-dots', () => { m.getCanvas().style.cursor = '' })
    return () => m.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function ensureLayers(m) {
    const d = dataRef.current
    if (!m.getSource(SRC)) m.addSource(SRC, { type: 'geojson', data: d.features || { type: 'FeatureCollection', features: [] }, promoteId: 'event_id' })
    if (!m.getSource(BOUNDARY)) m.addSource(BOUNDARY, { type: 'geojson', data: '/warsaw_boundary.geojson' })
    if (!m.getSource(AREAS)) m.addSource(AREAS, { type: 'geojson', data: d.busyAreas || EMPTY })
    if (!m.getSource(ROUTE)) m.addSource(ROUTE, { type: 'geojson', data: d.route || EMPTY })
    const before = firstSymbolLayer(m)
    // busy areas, Google "area busyness" style: pale yellow fill with a dotted golden outline (no labels).
    // Only the outer "busy" outline is drawn; the "very_busy" cores stay in the data.
    const outline = ['==', ['get', 'level'], 'busy']
    if (!m.getLayer('wl-busyareas-fill')) m.addLayer({ id: 'wl-busyareas-fill', type: 'fill', source: AREAS, filter: outline,
      paint: { 'fill-color': '#fcd462', 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.5, 16, 0.36] } }, before)
    if (!m.getLayer('wl-busyareas-line')) m.addLayer({ id: 'wl-busyareas-line', type: 'line', source: AREAS, filter: outline, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#f0ac00', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.6, 16, 2.6], 'line-dasharray': [0.1, 2] } }, before)
    if (!m.getLayer('wl-boundary-line')) m.addLayer({ id: 'wl-boundary-line', type: 'line', source: BOUNDARY, paint: { 'line-color': '#e7392b', 'line-width': 1.5, 'line-dasharray': [3, 3], 'line-opacity': 0.55 } }, before)
    if (!m.getLayer('wl-route-casing')) m.addLayer({ id: 'wl-route-casing', type: 'line', source: ROUTE, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 } })
    if (!m.getLayer('wl-route')) m.addLayer({ id: 'wl-route', type: 'line', source: ROUTE, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': vRef.current.accent, 'line-width': 3.5 } })
    if (!m.getLayer('wl-glow')) m.addLayer({ id: 'wl-glow', type: 'circle', source: SRC, paint: { 'circle-blur': 1, 'circle-opacity': 0.55 } })
    if (!m.getLayer('wl-dots')) m.addLayer({ id: 'wl-dots', type: 'circle', source: SRC, paint: {} })
    if (!m.getLayer('wl-starred')) m.addLayer({ id: 'wl-starred', type: 'circle', source: SRC, paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#f2a900', 'circle-stroke-width': 3 } })
    if (!m.getLayer('wl-selected')) m.addLayer({ id: 'wl-selected', type: 'circle', source: SRC, filter: ['==', ['get', 'event_id'], '__none__'], paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3, 'circle-radius': 16 } })
    styleMarkers(m, vRef.current)
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
  useEffect(() => { const m = map.current; if (m?.getSource(SRC) && features) { m.getSource(SRC).setData(features); openOnHome(m) } }, [features])
  useEffect(() => {
    const m = map.current
    if (!m?.getSource(AREAS) || !busyAreas) return
    m.getSource(AREAS).setData(busyAreas)
  }, [busyAreas])
  useEffect(() => { const m = map.current; if (m?.getSource(ROUTE)) m.getSource(ROUTE).setData(route || EMPTY) }, [route])
  useEffect(() => { const m = map.current; if (!m?.getLayer('wl-busyareas-fill')) return; for (const id of AREA_LAYERS) m.setLayoutProperty(id, 'visibility', values.busyAreas ? 'visible' : 'none') }, [values.busyAreas])
  useEffect(() => { const m = map.current; if (m?.getLayer('wl-route')) styleRoute(m, values) }, [values.routeStyle, values.accent])

  // "me": pulsing light-blue dot (HTML marker so CSS can animate it)
  useEffect(() => {
    const m = map.current
    if (!m) return
    if (!me || !values.showMe) { meMarker.current?.remove(); meMarker.current = null; return }
    if (!meMarker.current) {
      const el = document.createElement('div'); el.className = 'me-marker'; el.innerHTML = '<span class="ring"></span><span class="ring r2"></span><span class="core"></span><span class="me-label">You are here</span>'
      meMarker.current = new maplibregl.Marker({ element: el }).setLngLat(me).addTo(m)
    } else meMarker.current.setLngLat(me)
  }, [me, values.showMe])

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

  useEffect(() => { const m = map.current; if (m?.getLayer('wl-dots')) styleMarkers(m, values) }, [values.markerStyle, values.markerSize, values.colorBy, values.accent])

  function refreshFilters(m) {
    if (!m?.getLayer('wl-dots')) return
    const { favourites, favOnly } = dataRef.current
    const f = buildFilter(vRef.current, favourites, favOnly)
    m.setFilter('wl-dots', f)
    m.setFilter('wl-glow', f)
    m.setFilter('wl-starred', ['all', f, ['in', ['get', 'event_id'], ['literal', [...favourites]]]])
    m.setLayoutProperty('wl-starred', 'visibility', vRef.current.starredDefault || favOnly ? 'visible' : 'none')
  }
  useEffect(() => { refreshFilters(map.current) }, [values.showEvents, values.showPlaces, values.showPitches, values.showInvites, values.timeWindow, values.starredDefault, favourites, favOnly])

  // ---------- selected pulse ----------
  useEffect(() => {
    const m = map.current
    if (!m?.getLayer('wl-selected')) return
    m.setFilter('wl-selected', ['==', ['get', 'event_id'], selectedId ?? '__none__'])
    if (!selectedId) return
    let t0 = performance.now(), raf
    const tick = (t) => {
      const k = ((t - t0) / 1200) % 1
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

  return <div ref={el} className="map" />
})

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

