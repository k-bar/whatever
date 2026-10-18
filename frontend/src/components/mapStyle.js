/**
 * Map design. Base styles come from OpenFreeMap (free vector tiles, no key).
 * The editor's "Map design" params are applied on top by rewriting layer paint/layout.
 */
export const STYLE_URLS = {
  colour: 'https://tiles.openfreemap.org/styles/positron',
  grey: 'https://tiles.openfreemap.org/styles/positron',
  pastel: 'https://tiles.openfreemap.org/styles/positron',
  paper: 'https://tiles.openfreemap.org/styles/positron',
  bright: 'https://tiles.openfreemap.org/styles/bright',
  liberty: 'https://tiles.openfreemap.org/styles/liberty',
  fiord: 'https://tiles.openfreemap.org/styles/fiord',
  dark: 'https://tiles.openfreemap.org/styles/dark',
}
export const DARK_PALETTES = new Set(['dark', 'fiord'])

export function styleFor(values) {
  if (values.darkMode && !DARK_PALETTES.has(values.mapPalette)) return STYLE_URLS.dark
  return STYLE_URLS[values.mapPalette] || STYLE_URLS.grey
}

// Recolour rules by source-layer, for the "pastel" and "paper" palettes (built on positron).
const PALETTES = {
  // "colour": positron base, but nature gets real colours (footpaths stay plain white like the streets)
  colour: {
    background: '#f3f0ea', water: '#9cc7ea', landcover: '#cfe6c0', park: '#c6e3b3', landuse: '#ece8df',
    building: '#e6e1d8', buildingOutline: 'rgba(90,80,70,0.22)', road: '#ffffff', roadCasing: '#d9d3c7', boundary: '#b7ad9c', text: '#4d4a45',
    landcoverExpr: ['match', ['get', 'class'], ['wood', 'forest'], '#8fbf7f', ['grass', 'meadow', 'park', 'garden', 'recreation_ground', 'village_green'], '#cfe6c0', ['farmland', 'orchard'], '#e3e9c3', ['wetland'], '#b9d7cf', ['sand', 'beach'], '#efe3bf', '#d6e7cc'],
  },
  pastel: {
    background: '#fbf7ff', water: '#cfe3f5', landcover: '#dcefdb', park: '#d8ecd6', landuse: '#f3eef8',
    building: '#ece4f2', buildingOutline: '#dccfe6', road: '#ffffff', roadCasing: '#e9dff2', boundary: '#c9b8dd', text: '#6e5f80',
  },
  paper: {
    background: '#f6efe2', water: '#bcd3dc', landcover: '#e2e6cf', park: '#dfe5c8', landuse: '#efe6d3',
    building: '#eadfca', buildingOutline: '#d9cbb0', road: '#fffaf0', roadCasing: '#dccfb8', boundary: '#b8a78a', text: '#5c5240',
  },
}
const WATER = { azure: '#7fc4f0', ink: '#1b2a4a', mint: '#9fe3cf' }

// Land use, coloured by OpenMapTiles `landuse.class` (from OpenStreetMap). Positron only paints
// residential, so on the light positron palettes we draw every class ourselves.
export const LANDUSE = [
  { key: 'residential', label: 'Residential', color: '#ece3d6', classes: ['residential', 'garages'] },
  { key: 'commercial', label: 'Commercial & retail', color: '#f7dccb', classes: ['commercial', 'retail'] },
  { key: 'industrial', label: 'Industrial & rail', color: '#e3dfeb', classes: ['industrial', 'railway', 'bus_station'] },
  { key: 'education', label: 'Schools & universities', color: '#f3e8c4', classes: ['school', 'university', 'college', 'kindergarten', 'library'] },
  { key: 'health', label: 'Hospitals', color: '#f5d8da', classes: ['hospital'] },
  { key: 'sport', label: 'Sport & stadiums', color: '#cfe9da', classes: ['stadium', 'pitch', 'track', 'playground'] },
  { key: 'leisure', label: 'Zoo & theme parks', color: '#d8ecc4', classes: ['zoo', 'theme_park'] },
  { key: 'cemetery', label: 'Cemeteries', color: '#d9e0d1', classes: ['cemetery'] },
  { key: 'military', label: 'Military', color: '#e2ddd6', classes: ['military'] },
]
const LANDUSE_PALETTES = new Set(['colour', 'pastel', 'paper'])
const RESIDENTIAL = ['residential', 'garages']
const LANDUSE_HIDDEN_KEY = 'warszawa-live.landuse-hidden.v1'
let landuseHidden = new Set((() => { try { return JSON.parse(localStorage.getItem(LANDUSE_HIDDEN_KEY) || '[]') } catch { return [] } })())

export const landuseActive = (v) => v.landuse !== false && !v.darkMode && LANDUSE_PALETTES.has(v.mapPalette)
export const getLanduseHidden = () => new Set(landuseHidden)

function landuseColorExpr() {
  const m = ['match', ['get', 'class']]
  for (const c of LANDUSE) if (!landuseHidden.has(c.key)) m.push(c.classes, c.color)
  return m.length > 2 ? [...m, 'rgba(0,0,0,0)'] : 'rgba(0,0,0,0)'
}

/** Show/hide land-use classes from the map key (remembered per browser). */
export function setLanduseHidden(map, hidden) {
  landuseHidden = new Set(hidden)
  try { localStorage.setItem(LANDUSE_HIDDEN_KEY, JSON.stringify([...landuseHidden])) } catch { /* private mode */ }
  for (const id of ['wl-landuse-res', 'wl-landuse']) if (map?.getLayer(id)) map.setPaintProperty(id, 'fill-color', landuseColorExpr())
}

function applyLanduse(map, v, layers) {
  const on = landuseActive(v)
  if (map.getLayer('landuse_residential')) map.setLayoutProperty('landuse_residential', 'visibility', on ? 'none' : 'visible')
  if (!on) {
    for (const id of ['wl-landuse', 'wl-landuse-res']) if (map.getLayer(id)) map.removeLayer(id)
    return
  }
  if (!map.getLayer('wl-landuse-res')) {
    const src = layers.find((l) => l['source-layer'] === 'landuse')?.source || 'openmaptiles'
    // straight above the background: parks, woods and water still draw on top
    const beforeId = layers.find((l) => l.type !== 'background')?.id
    map.addLayer({ id: 'wl-landuse-res', type: 'fill', source: src, 'source-layer': 'landuse',
      filter: ['in', ['get', 'class'], ['literal', RESIDENTIAL]], paint: { 'fill-opacity': 1 } }, beforeId)
    map.addLayer({ id: 'wl-landuse', type: 'fill', source: src, 'source-layer': 'landuse',
      filter: ['!', ['in', ['get', 'class'], ['literal', RESIDENTIAL]]], paint: { 'fill-opacity': 1, 'fill-outline-color': 'rgba(90,80,70,0.12)' } }, beforeId)
  }
  for (const id of ['wl-landuse-res', 'wl-landuse']) map.setPaintProperty(id, 'fill-color', landuseColorExpr())
}

export function applyMapDesign(map, v) {
  // not isStyleLoaded(): that stays false while tiles or our own new sources load, which is always the case
  // right after a style switch, and the design (labels, palette, buildings…) was silently skipped
  let layers
  try { layers = map.getStyle()?.layers } catch { return } // mid style switch: style.load applies it
  if (!layers) return
  // dark mode swaps in the dark base style: the light palettes' recolouring must not be painted onto it
  const pal = v.darkMode && !DARK_PALETTES.has(v.mapPalette) ? null : PALETTES[v.mapPalette]
  const labelFactor = { none: 0, small: 0.8, normal: 1, large: 1.45 }[v.streetLabels] ?? 1
  const set = (fn) => { try { fn() } catch { /* layer without that property */ } }

  for (const l of layers) {
    if (l.id.startsWith('wl-')) continue
    const sl = l['source-layer'] || ''
    const id = l.id.toLowerCase()

    // --- street names ---
    if (l.type === 'symbol' && (sl === 'transportation_name' || id.includes('road_label') || id.includes('street'))) {
      set(() => map.setLayoutProperty(l.id, 'visibility', labelFactor ? 'visible' : 'none'))
      if (labelFactor) set(() => map.setLayoutProperty(l.id, 'text-size', ['interpolate', ['linear'], ['zoom'], 11, 9 * labelFactor, 14, 11 * labelFactor, 18, 15 * labelFactor]))
    }
    // --- POI labels ---
    if (l.type === 'symbol' && (sl === 'poi' || id.includes('poi'))) set(() => map.setLayoutProperty(l.id, 'visibility', v.poiLabels ? 'visible' : 'none'))

    // --- buildings ---
    if (sl === 'building' && l.type !== 'fill-extrusion') {
      set(() => map.setLayoutProperty(l.id, 'visibility', v.buildings === 'hide' || v.buildings === '3d' ? 'none' : 'visible'))
    }

    // --- borders ---
    if (l.type === 'fill' && (sl === 'building' || sl === 'landuse' || sl === 'landcover' || sl === 'park')) {
      const color = v.borders === 'none' ? 'rgba(0,0,0,0)' : v.borders === 'bold' ? (pal?.buildingOutline || 'rgba(60,60,70,0.55)') : (pal?.buildingOutline || 'rgba(60,60,70,0.18)')
      set(() => map.setPaintProperty(l.id, 'fill-outline-color', color))
    }
    if (l.type === 'line' && (sl === 'boundary' || id.includes('boundary') || id.includes('admin'))) {
      const w = v.borders === 'none' ? 0 : v.borders === 'bold' ? 2.2 : 1
      set(() => map.setPaintProperty(l.id, 'line-width', w))
      if (pal) set(() => map.setPaintProperty(l.id, 'line-color', pal.boundary))
    }
    if (l.type === 'line' && sl === 'transportation' && (id.includes('casing') || id.includes('outline'))) {
      set(() => map.setLayoutProperty(l.id, 'visibility', v.borders === 'none' ? 'none' : 'visible'))
      if (pal) set(() => map.setPaintProperty(l.id, 'line-color', pal.roadCasing))
    }

    // --- palette recolour ---
    if (pal) {
      if (l.type === 'background') set(() => map.setPaintProperty(l.id, 'background-color', pal.background))
      if (l.type === 'fill' && sl === 'water') set(() => map.setPaintProperty(l.id, 'fill-color', pal.water))
      if (l.type === 'fill' && sl === 'landcover') set(() => map.setPaintProperty(l.id, 'fill-color', pal.landcoverExpr || pal.landcover))
      if (l.type === 'fill' && sl === 'park') set(() => map.setPaintProperty(l.id, 'fill-color', pal.park))
      if (l.type === 'fill' && sl === 'landuse') set(() => map.setPaintProperty(l.id, 'fill-color', pal.landuse))
      if (l.type === 'fill' && sl === 'building') set(() => map.setPaintProperty(l.id, 'fill-color', pal.building))
      if (l.type === 'line' && sl === 'transportation' && !id.includes('casing') && !id.includes('outline')) set(() => map.setPaintProperty(l.id, 'line-color', pal.road))
      if (l.type === 'symbol') set(() => map.setPaintProperty(l.id, 'text-color', pal.text))
    }
    // --- Vistula tint ---
    if (l.type === 'fill' && sl === 'water' && v.waterTint !== 'default') set(() => map.setPaintProperty(l.id, 'fill-color', WATER[v.waterTint]))
  }

  set(() => applyLanduse(map, v, layers))

  // --- 3D buildings ---
  if (v.buildings === '3d') {
    if (!map.getLayer('wl-3d')) {
      const src = layers.find((l) => l['source-layer'] === 'building')?.source || 'openmaptiles'
      map.addLayer({
        id: 'wl-3d', type: 'fill-extrusion', source: src, 'source-layer': 'building', minzoom: 13,
        paint: {
          'fill-extrusion-color': pal?.building || (v.darkMode || DARK_PALETTES.has(v.mapPalette) ? '#2a3140' : '#e4e1dc'),
          'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 12],
          'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
          'fill-extrusion-opacity': 0.85,
        },
      }, firstSymbolLayer(map))
    }
    if (map.getPitch() < 30) map.easeTo({ pitch: 50, duration: 800 })
  } else {
    if (map.getLayer('wl-3d')) map.removeLayer('wl-3d')
    if (map.getPitch() > 0) map.easeTo({ pitch: 0, duration: 600 })
  }
}

export function firstSymbolLayer(map) {
  return (map.getStyle().layers || []).find((l) => l.type === 'symbol')?.id
}

