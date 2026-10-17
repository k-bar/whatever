/**
 * "In the city" map layers from Warsaw open data (Kamil's datasets, served by the backend):
 *   toilets  GET /places?category=toilets  public toilets, with opening hours
 *   aed      GET /places?category=aed      defibrillators
 *   walks    GET /routes                   the city's tourist walking routes (LineStrings + stops)
 * They live on their own sources/layers, apart from the event pins, so they never change pin counts or
 * the home view. Each is switched on from the toolbar's pin box (config: showToilets / showAed / showWalks).
 * Toilets and AEDs are for the walk you're on: they only appear within AMENITY_RADIUS_M of your route
 * (the journey to an open box, and an open walking route's line), see `alongPaths`.
 */

export const CITY_LAYERS = [
  { id: 'toilets', param: 'showToilets', label: 'Toilets', emoji: '🚻' },
  { id: 'aed', param: 'showAed', label: 'Defibrillators (AED)', emoji: '❤️' },
  { id: 'walks', param: 'showWalks', label: 'Walking routes', emoji: '🚶' },
]

export const AMENITY_RADIUS_M = 600
const NEAR_PATH = ['toilets', 'aed']

/**
 * The lines you're walking: the route on the map (a FeatureCollection), every open box's journey (so
 * tapping a toilet doesn't hide the ones along your first route) and any open walking route's line.
 */
export function walkPaths(route, boxes = []) {
  const lines = [...(route?.features || []).map((f) => f.geometry), ...boxes.flatMap((b) => [b.journey?.geometry, b.feature?.line])]
  return lines.filter(Boolean).flatMap((g) => (g.type === 'MultiLineString' ? g.coordinates : g.type === 'LineString' ? [g.coordinates] : []))
}

/**
 * The city layers with toilets and AEDs cut down to those within `radius` metres of the paths
 * (none when there's no path). Flat metres around Warsaw's latitude: plenty for a few hundred metres.
 */
export function alongPaths(city, paths, radius = AMENITY_RADIUS_M) {
  const kx = 111320 * Math.cos((52.23 * Math.PI) / 180), ky = 110540
  const segs = []
  for (const line of paths) for (let i = 1; i < line.length; i++) {
    const [ax, ay] = [line[i - 1][0] * kx, line[i - 1][1] * ky], [bx, by] = [line[i][0] * kx, line[i][1] * ky]
    segs.push([ax, ay, bx, by, Math.min(ax, bx) - radius, Math.min(ay, by) - radius, Math.max(ax, bx) + radius, Math.max(ay, by) + radius])
  }
  if (paths.length && !segs.length) for (const [x, y] of paths.flat()) segs.push([x * kx, y * ky, x * kx, y * ky, x * kx - radius, y * ky - radius, x * kx + radius, y * ky + radius])
  const r2 = radius * radius
  const near = ([lng, lat]) => {
    const px = lng * kx, py = lat * ky
    return segs.some(([ax, ay, bx, by, x0, y0, x1, y1]) => {
      if (px < x0 || px > x1 || py < y0 || py > y1) return false
      const dx = bx - ax, dy = by - ay, len = dx * dx + dy * dy
      const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0
      const ex = ax + t * dx - px, ey = ay + t * dy - py
      return ex * ex + ey * ey <= r2
    })
  }
  const out = { ...city }
  for (const id of NEAR_PATH) if (city[id]) out[id] = { ...city[id], features: segs.length ? city[id].features.filter((f) => f.geometry?.type === 'Point' && near(f.geometry.coordinates)) : [] }
  return out
}

const AMENITIES = 'wl-amenities', WALKS = 'wl-walks', STOPS = 'wl-walk-stops'
export const CITY_CLICK_LAYERS = { amenity: 'wl-amenities', walk: 'wl-walks-hit' }
const EMPTY = { type: 'FeatureCollection', features: [] }
// one colour per route, from the app's category palette
const WALK_COLORS = ['#e7392b', '#2b6be7', '#0fa37f', '#7c4dff', '#f97316', '#ec4899', '#0ea5e9', '#d97706', '#14b8a6']

/** Toilets + AEDs in one source, tagged with `amenity`. */
export function amenitiesData(city) {
  const tag = (fc, amenity) => (fc?.features || []).map((f) => ({ ...f, properties: { ...f.properties, amenity } }))
  return { type: 'FeatureCollection', features: [...tag(city.toilets, 'toilets'), ...tag(city.aed, 'aed')] }
}

/** Routes with a stable key and colour; their stops as points. */
export function walksData(city) {
  const routes = (city.walks?.features || []).map((f, i) => ({
    ...f, properties: { ...f.properties, walk_key: `walk-${i}`, color: WALK_COLORS[i % WALK_COLORS.length] },
  }))
  const stops = routes.flatMap((r) => (r.properties.points || []).map((p) => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
    properties: { name: p.name, color: r.properties.color, walk_key: r.properties.walk_key },
  })))
  return { routes: { type: 'FeatureCollection', features: routes }, stops: { type: 'FeatureCollection', features: stops } }
}

/** Small rounded-square badges drawn on a canvas (2× for sharp edges): "WC" and the AED heart. */
function badge(draw) {
  const s = 40, r = 2, c = document.createElement('canvas')
  c.width = c.height = s * r
  const g = c.getContext('2d')
  g.scale(r, r)
  g.beginPath(); g.roundRect(2, 2, s - 4, s - 4, 11); g.fillStyle = '#ffffff'; g.fill() // white rim
  g.beginPath(); g.roundRect(5, 5, s - 10, s - 10, 8)
  draw(g, s)
  return g.getImageData(0, 0, s * r, s * r)
}
const ICONS = {
  'syr-wc': () => badge((g, s) => {
    g.fillStyle = '#2b6be7'; g.fill()
    g.fillStyle = '#ffffff'; g.font = '800 13px Inter, system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'
    g.fillText('WC', s / 2, s / 2 + 1)
  }),
  'syr-aed': () => badge((g, s) => {
    g.fillStyle = '#0fa37f'; g.fill()
    const cx = s / 2, cy = s / 2 + 1 // white heart
    g.beginPath(); g.moveTo(cx, cy + 9)
    g.bezierCurveTo(cx - 13, cy, cx - 9, cy - 11, cx, cy - 5)
    g.bezierCurveTo(cx + 9, cy - 11, cx + 13, cy, cx, cy + 9)
    g.fillStyle = '#ffffff'; g.fill()
    g.beginPath(); g.moveTo(cx + 1.5, cy - 6); g.lineTo(cx - 3, cy + 1); g.lineTo(cx, cy + 1); g.lineTo(cx - 1.5, cy + 7); g.lineTo(cx + 3.5, cy - 1); g.lineTo(cx + 0.5, cy - 1); g.closePath()
    g.fillStyle = '#0fa37f'; g.fill() // lightning bolt through it
  }),
}

/** Add sources, icons and layers (idempotent; runs again after every style switch). */
export function ensureCityLayers(m, city, beforeLabels, beforePins) {
  for (const [id, make] of Object.entries(ICONS)) if (!m.hasImage(id)) m.addImage(id, make(), { pixelRatio: 2 })
  const walks = walksData(city)
  if (!m.getSource(AMENITIES)) m.addSource(AMENITIES, { type: 'geojson', data: amenitiesData(city) })
  if (!m.getSource(WALKS)) m.addSource(WALKS, { type: 'geojson', data: walks.routes })
  if (!m.getSource(STOPS)) m.addSource(STOPS, { type: 'geojson', data: walks.stops })

  // walking routes: a dotted ribbon (white casing + coloured dots), like the busy areas' outline
  const width = (k) => ['interpolate', ['linear'], ['zoom'], 11, 2.4 * k, 14, 3.6 * k, 17, 5.5 * k]
  if (!m.getLayer('wl-walks-glow')) m.addLayer({ id: 'wl-walks-glow', type: 'line', source: WALKS, filter: ['==', ['get', 'walk_key'], '__none__'],
    layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': width(4), 'line-blur': 6, 'line-opacity': 0.35 } }, beforeLabels)
  if (!m.getLayer('wl-walks-casing')) m.addLayer({ id: 'wl-walks-casing', type: 'line', source: WALKS,
    layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': width(2.4), 'line-opacity': 0.92 } }, beforeLabels)
  if (!m.getLayer('wl-walks')) m.addLayer({ id: 'wl-walks', type: 'line', source: WALKS,
    layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': width(1), 'line-dasharray': [0.1, 1.9] } }, beforeLabels)
  if (!m.getLayer('wl-walks-hit')) m.addLayer({ id: 'wl-walks-hit', type: 'line', source: WALKS, paint: { 'line-color': '#000', 'line-width': 24, 'line-opacity': 0 } }, beforeLabels)
  if (!m.getLayer('wl-walk-stops')) m.addLayer({ id: 'wl-walk-stops', type: 'circle', source: STOPS, minzoom: 12.5,
    paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 12.5, 3, 16, 5], 'circle-color': '#ffffff', 'circle-stroke-color': ['get', 'color'], 'circle-stroke-width': 2.2 } }, beforePins)
  if (!m.getLayer('wl-walks-label')) m.addLayer({ id: 'wl-walks-label', type: 'symbol', source: WALKS, minzoom: 11.5,
    layout: { 'symbol-placement': 'line', 'symbol-spacing': 420, 'text-field': ['get', 'title'], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-letter-spacing': 0.02, 'text-max-angle': 30 },
    paint: { 'text-color': ['get', 'color'], 'text-halo-color': '#ffffff', 'text-halo-width': 2.2 } }, beforePins)

  // toilets + AEDs: badges, decluttered by MapLibre's collision detection when zoomed out
  if (!m.getLayer(AMENITIES)) m.addLayer({ id: AMENITIES, type: 'symbol', source: AMENITIES, minzoom: 11,
    layout: { 'icon-image': ['match', ['get', 'amenity'], 'aed', 'syr-aed', 'syr-wc'], 'icon-size': ['interpolate', ['linear'], ['zoom'], 11, 0.45, 13, 0.6, 15, 0.8, 17, 0.95], 'icon-padding': 1 } }, beforePins)
}

export function setCityData(m, city) {
  const walks = walksData(city)
  m.getSource(AMENITIES)?.setData(amenitiesData(city))
  m.getSource(WALKS)?.setData(walks.routes)
  m.getSource(STOPS)?.setData(walks.stops)
}

const WALK_LAYERS = ['wl-walks-glow', 'wl-walks-casing', 'wl-walks', 'wl-walks-hit', 'wl-walk-stops', 'wl-walks-label']
export function setCityVisibility(m, v) {
  if (!m.getLayer(AMENITIES)) return
  const on = CITY_LAYERS.filter((l) => l.id !== 'walks' && v[l.param]).map((l) => l.id)
  m.setFilter(AMENITIES, ['in', ['get', 'amenity'], ['literal', on]])
  m.setLayoutProperty(AMENITIES, 'visibility', on.length ? 'visible' : 'none')
  for (const id of WALK_LAYERS) m.setLayoutProperty(id, 'visibility', v.showWalks ? 'visible' : 'none')
}

/** The route whose box is open glows. */
export function highlightWalk(m, key) {
  if (m.getLayer('wl-walks-glow')) m.setFilter('wl-walks-glow', ['==', ['get', 'walk_key'], key || '__none__'])
}

/** The open map box for a route: a Point at its first stop (boxes / journeys work on points) + the full line. */
export function walkBoxFeature(route) {
  const p = route.properties
  const first = p.points?.[0]
  const start = first ? [first.lng, first.lat] : route.geometry.coordinates[0]
  return { type: 'Feature', id: p.walk_key, geometry: { type: 'Point', coordinates: start }, properties: { ...p, event_id: p.walk_key, kind: 'walk', categories: ['culture'] }, line: route.geometry }
}
