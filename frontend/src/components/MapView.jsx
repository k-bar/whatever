import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useConfig } from '../config/store'
import { WARSAW_BBOX } from '../data/api'
import { categoryMatchExpr } from '../data/categories'
import { applyMapDesign, firstSymbolLayer, HEAT_PALETTES, styleFor } from './mapStyle'

const SRC = 'wl-features', BUSY = 'wl-busy', BOUNDARY = 'wl-boundary', TRAFFIC = 'wl-traffic', ROUTE = 'wl-route'
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

export const MapView = forwardRef(function MapView({ features, busy, traffic, route, me, heat, favourites, favOnly, selectedId, onPick, onReady, onMove }, ref) {
  const { values } = useConfig()
  const el = useRef(null)
  const map = useRef(null)
  const vRef = useRef(values)
  vRef.current = values
  // latest props for handlers registered once (style.load fires again after every setStyle)
  const dataRef = useRef({ features, busy, heat, favourites, favOnly, traffic, route })
  dataRef.current = { features, busy, heat, favourites, favOnly, traffic, route }
  const meMarker = useRef(null)
  const styleKey = styleFor(values)

  useImperativeHandle(ref, () => ({
    zoomBy: (d) => map.current?.zoomTo(map.current.getZoom() + d, { duration: 350 }),
    home: () => map.current?.fitBounds([[WARSAW_BBOX[0], WARSAW_BBOX[1]], [WARSAW_BBOX[2], WARSAW_BBOX[3]]], { padding: 40, pitch: 0, bearing: 0, duration: 1200 }),
    flyTo: (f, zoom = 15) => map.current?.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.current.getZoom(), zoom), duration: 1100, essential: true,
      padding: window.innerWidth < 768 ? { bottom: window.innerHeight * 0.45 } : { right: 380 } }),
    getZoom: () => map.current?.getZoom(),
    getMap: () => map.current,
  }))

  // ---------- init ----------
  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current, style: styleKey, center: [21.012, 52.232], zoom: 11.6, minZoom: 9.5, maxZoom: 19,
      maxBounds: [[20.4, 51.9], [21.8, 52.6]], attributionControl: { compact: true }, antialias: true, fadeDuration: 150,
    })
    map.current = m
    m.on('load', () => { ensureLayers(m); applyMapDesign(m, vRef.current); onReady?.() })
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
    if (!m.getSource(BUSY)) m.addSource(BUSY, { type: 'geojson', data: d.busy || { type: 'FeatureCollection', features: [] } })
    if (!m.getSource(BOUNDARY)) m.addSource(BOUNDARY, { type: 'geojson', data: '/warsaw_boundary.geojson' })
    if (!m.getSource(TRAFFIC)) m.addSource(TRAFFIC, { type: 'geojson', data: d.traffic || EMPTY })
    if (!m.getSource(ROUTE)) m.addSource(ROUTE, { type: 'geojson', data: d.route || EMPTY })
    const before = firstSymbolLayer(m)
    if (!m.getLayer('wl-traffic-fill')) m.addLayer({ id: 'wl-traffic-fill', type: 'fill', source: TRAFFIC, paint: { 'fill-color': '#f2b705', 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.18, 15, 0.28] } }, before)
    if (!m.getLayer('wl-traffic-line')) m.addLayer({ id: 'wl-traffic-line', type: 'line', source: TRAFFIC, paint: { 'line-color': '#d9a400', 'line-width': 1.5, 'line-opacity': 0.8 } }, before)
    if (!m.getLayer('wl-boundary-line')) m.addLayer({ id: 'wl-boundary-line', type: 'line', source: BOUNDARY, paint: { 'line-color': '#e7392b', 'line-width': 1.5, 'line-dasharray': [3, 3], 'line-opacity': 0.55 } }, before)
    if (!m.getLayer('wl-heat')) m.addLayer({ id: 'wl-heat', type: 'heatmap', source: BUSY, layout: { visibility: d.heat ? 'visible' : 'none' }, paint: { 'heatmap-weight': ['get', 'weight'] } })
    if (!m.getLayer('wl-route-casing')) m.addLayer({ id: 'wl-route-casing', type: 'line', source: ROUTE, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 } })
    if (!m.getLayer('wl-route')) m.addLayer({ id: 'wl-route', type: 'line', source: ROUTE, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': vRef.current.accent, 'line-width': 3.5 } })
    if (!m.getLayer('wl-glow')) m.addLayer({ id: 'wl-glow', type: 'circle', source: SRC, paint: { 'circle-blur': 1, 'circle-opacity': 0.55 } })
    if (!m.getLayer('wl-dots')) m.addLayer({ id: 'wl-dots', type: 'circle', source: SRC, paint: {} })
    if (!m.getLayer('wl-starred')) m.addLayer({ id: 'wl-starred', type: 'circle', source: SRC, paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#f2a900', 'circle-stroke-width': 3 } })
    if (!m.getLayer('wl-selected')) m.addLayer({ id: 'wl-selected', type: 'circle', source: SRC, filter: ['==', ['get', 'event_id'], '__none__'], paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3, 'circle-radius': 16 } })
    styleMarkers(m, vRef.current)
    styleHeat(m, vRef.current)
    refreshFilters(m)
    styleRoute(m, vRef.current)
    m.setLayoutProperty('wl-traffic-fill', 'visibility', vRef.current.trafficAreas ? 'visible' : 'none')
    m.setLayoutProperty('wl-traffic-line', 'visibility', vRef.current.trafficAreas ? 'visible' : 'none')
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
  useEffect(() => { const m = map.current; if (m?.getSource(SRC) && features) m.getSource(SRC).setData(features) }, [features])
  useEffect(() => { const m = map.current; if (m?.getSource(BUSY) && busy) m.getSource(BUSY).setData(busy) }, [busy])
  useEffect(() => { const m = map.current; if (m?.getSource(TRAFFIC) && traffic) m.getSource(TRAFFIC).setData(traffic) }, [traffic])
  useEffect(() => { const m = map.current; if (m?.getSource(ROUTE)) m.getSource(ROUTE).setData(route || EMPTY) }, [route])
  useEffect(() => { const m = map.current; if (!m?.getLayer('wl-traffic-fill')) return; for (const id of ['wl-traffic-fill', 'wl-traffic-line']) m.setLayoutProperty(id, 'visibility', values.trafficAreas ? 'visible' : 'none') }, [values.trafficAreas])
  useEffect(() => { const m = map.current; if (m?.getLayer('wl-route')) styleRoute(m, values) }, [values.routeStyle, values.accent])

  // "me": pulsing light-blue dot (HTML marker so CSS can animate it)
  useEffect(() => {
    const m = map.current
    if (!m) return
    if (!me || !values.showMe) { meMarker.current?.remove(); meMarker.current = null; return }
    if (!meMarker.current) {
      const el = document.createElement('div'); el.className = 'me-marker'; el.innerHTML = '<span class="ring"></span><span class="ring r2"></span><span class="core"></span>'
      meMarker.current = new maplibregl.Marker({ element: el }).setLngLat(me).addTo(m)
    } else meMarker.current.setLngLat(me)
  }, [me, values.showMe])

  // ---------- design params ----------
  useEffect(() => {
    const m = map.current
    if (!m?.isStyleLoaded()) return
    applyMapDesign(m, values)
  }, [values.streetLabels, values.poiLabels, values.borders, values.buildings, values.waterTint, values.mapPalette, values.cityBoundary])

  useEffect(() => {
    const m = map.current
    if (!m?.getLayer('wl-boundary-line')) return
    m.setLayoutProperty('wl-boundary-line', 'visibility', values.cityBoundary ? 'visible' : 'none')
    m.setPaintProperty('wl-boundary-line', 'line-color', values.accent)
  }, [values.cityBoundary, values.accent])

  useEffect(() => { const m = map.current; if (m?.getLayer('wl-dots')) styleMarkers(m, values) }, [values.markerStyle, values.markerSize, values.colorBy, values.accent])
  useEffect(() => { const m = map.current; if (m?.getLayer('wl-heat')) styleHeat(m, values) }, [values.heatPalette, values.heatIntensity, values.heatRadius, values.heatOpacity, values.accent])
  useEffect(() => { const m = map.current; if (m?.getLayer('wl-heat')) m.setLayoutProperty('wl-heat', 'visibility', heat ? 'visible' : 'none') }, [heat])

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

function styleHeat(m, v) {
  const stops = HEAT_PALETTES[v.heatPalette].map((c) => c === 'ACCENT' ? v.accent : c === 'ACCENT70' ? `color-mix(in srgb, ${v.accent} 70%, transparent)` : c === 'ACCENT40' ? `color-mix(in srgb, ${v.accent} 40%, transparent)` : c)
  // maplibre needs plain colours; resolve color-mix via a canvas
  const resolved = stops.map(resolveColor)
  m.setPaintProperty('wl-heat', 'heatmap-color', ['interpolate', ['linear'], ['heatmap-density'], 0, resolved[0], 0.15, resolved[1], 0.35, resolved[2], 0.6, resolved[3], 0.85, resolved[4], 1, resolved[5]])
  m.setPaintProperty('wl-heat', 'heatmap-intensity', ['interpolate', ['linear'], ['zoom'], 10, 0.6 * v.heatIntensity, 15, 2.2 * v.heatIntensity])
  m.setPaintProperty('wl-heat', 'heatmap-radius', ['interpolate', ['linear'], ['zoom'], 10, v.heatRadius * 0.6, 14, v.heatRadius, 17, v.heatRadius * 2.4])
  m.setPaintProperty('wl-heat', 'heatmap-opacity', v.heatOpacity)
}

let ctx
function resolveColor(c) {
  if (!c.startsWith('color-mix')) return c
  const m = c.match(/,\s*(#[0-9a-f]{3,8})\s+(\d+)%/i)
  if (!m) return c
  ctx ||= document.createElement('canvas').getContext('2d')
  ctx.fillStyle = m[1]
  const hex = ctx.fillStyle
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${Number(m[2]) / 100})`
}
