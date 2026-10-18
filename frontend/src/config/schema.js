/**
 * Interface editor schema.
 *
 * Every visual knob of the UI is declared here once. The editor tray renders this list,
 * the store persists it, and `applyConfig()` turns it into CSS variables / data-attributes
 * (and map-side settings) that components read. To add a tweakable thing:
 *   1. add a param below (pick a `type`),
 *   2. consume it: either a CSS var `--<id>` / `data-<id>` on <html> (set automatically),
 *      or read `useConfig().values.<id>` in a component.
 * Nothing here is decorative: each param is wired to something on screen.
 *
 * types: select {options:[{value,label}]}, range {min,max,step,unit}, toggle, color {options:[hex]}, text
 */

const FONTS = ['Manrope', 'Inter', 'Space Grotesk', 'DM Sans', 'Syne', 'Playfair Display', 'Fraunces', 'JetBrains Mono']
const fontOptions = FONTS.map((f) => ({ value: f, label: f }))

export const SECTIONS = [
  {
    id: 'typography', label: 'Typography',
    params: [
      { id: 'titleFont', label: 'Title font', type: 'select', options: fontOptions, default: 'Manrope' },
      { id: 'titleSize', label: 'Title font size', type: 'range', min: 14, max: 30, step: 1, unit: 'px', default: 19 },
      { id: 'titleWeight', label: 'Title weight', type: 'select', default: '700', options: [
        { value: '500', label: 'Medium' }, { value: '600', label: 'Semibold' }, { value: '700', label: 'Bold' }, { value: '800', label: 'Black' }] },
      { id: 'bodyFont', label: 'Body font', type: 'select', options: fontOptions, default: 'Inter' },
      { id: 'bodySize', label: 'Body font size', type: 'range', min: 12, max: 18, step: 1, unit: 'px', default: 14 },
      { id: 'letterSpacing', label: 'Title letter spacing', type: 'range', min: -0.04, max: 0.08, step: 0.01, unit: 'em', default: -0.01 },
    ],
  },
  {
    id: 'surfaces', label: 'Surfaces & buttons',
    params: [
      // Surfaces are always solid white (solid dark in dark mode): no glass / transparency knobs on purpose.
      { id: 'buttonStyle', label: 'Button style', type: 'select', default: 'glass', options: [
        { value: 'glass', label: 'White' }, { value: 'filled', label: 'Filled' }, { value: 'soft', label: 'Soft' }, { value: 'outline', label: 'Outline' }] },
      { id: 'accent', label: 'Accent colour', type: 'color', default: '#e7392b',
        options: ['#e7392b', '#ff6b4a', '#2b6be7', '#7c4dff', '#0fa37f', '#f2a900', '#111111'] },
      { id: 'radius', label: 'Corner radius', type: 'range', min: 6, max: 32, step: 1, unit: 'px', default: 22 },
      { id: 'shadow', label: 'Shadow depth', type: 'select', default: 'soft', options: [
        { value: 'none', label: 'None' }, { value: 'soft', label: 'Soft' }, { value: 'deep', label: 'Deep' }, { value: 'hard', label: 'Hard offset' }] },
      { id: 'controlSize', label: 'Control size', type: 'range', min: 36, max: 60, step: 2, unit: 'px', default: 48 },
    ],
  },
  {
    id: 'search', label: 'Search bar',
    params: [
      { id: 'searchGlow', label: 'Search bar glow style', type: 'select', default: 'soft', options: [
        { value: 'none', label: 'None' }, { value: 'soft', label: 'Soft halo' }, { value: 'neon', label: 'Neon' },
        { value: 'pulse', label: 'Pulse' }, { value: 'aurora', label: 'Aurora ring' }] },
      { id: 'searchWidth', label: 'Search bar width', type: 'range', min: 380, max: 780, step: 10, unit: 'px', default: 560 },
      { id: 'searchHeight', label: 'Search bar height', type: 'range', min: 46, max: 72, step: 2, unit: 'px', default: 58 },
      { id: 'searchPanel', label: 'Focus panel (recents / categories / chat)', type: 'toggle', default: true },
      { id: 'searchPlaceholder', label: 'Placeholder text', type: 'text', default: "What's the plan today?" },
    ],
  },
  {
    id: 'map', label: 'Map design',
    params: [
      { id: 'mapPalette', label: 'Map palette', type: 'select', default: 'colour', options: [
        { value: 'colour', label: 'Colour (parks, water, paths)' }, { value: 'grey', label: 'Grey (Positron)' }, { value: 'pastel', label: 'Pastel' }, { value: 'paper', label: 'Warm paper' },
        { value: 'bright', label: 'Bright colours' }, { value: 'liberty', label: 'Liberty' }, { value: 'fiord', label: 'Fiord (blue dark)' }, { value: 'dark', label: 'Dark matter' }] },
      { id: 'landuse', label: 'Land-use colours (residential, commercial…)', type: 'toggle', default: true },
      { id: 'landuseLegend', label: 'Land-use key (in Data sources)', type: 'toggle', default: true },
      { id: 'streetLabels', label: 'Street names', type: 'select', default: 'normal', options: [
        { value: 'none', label: 'Hidden' }, { value: 'small', label: 'Small' }, { value: 'normal', label: 'Normal' }, { value: 'large', label: 'Large' }] },
      { id: 'poiLabels', label: 'Place labels (POI)', type: 'toggle', default: false },
      { id: 'borders', label: 'Object borders', type: 'select', default: 'thin', options: [
        { value: 'none', label: 'No borders' }, { value: 'thin', label: 'Thin' }, { value: 'bold', label: 'Bold' }] },
      { id: 'buildings', label: 'Buildings', type: 'select', default: 'flat', options: [
        { value: 'hide', label: 'Hidden' }, { value: 'flat', label: 'Flat' }, { value: '3d', label: '3D extruded' }] },
      { id: 'waterTint', label: 'Vistula tint', type: 'select', default: 'default', options: [
        { value: 'default', label: 'Default' }, { value: 'azure', label: 'Azure' }, { value: 'ink', label: 'Ink' }, { value: 'mint', label: 'Mint' }] },
      { id: 'mapSaturation', label: 'Map saturation', type: 'range', min: 0, max: 1.6, step: 0.1, default: 1 },
      { id: 'cityBoundary', label: 'City boundary line', type: 'toggle', default: true },
      { id: 'busyAreas', label: 'Busy areas (golden outlines)', type: 'toggle', default: true },
      { id: 'showMe', label: 'My position (IP based)', type: 'toggle', default: true },
      { id: 'meStyle', label: 'My position marker', type: 'select', default: 'syrenka', options: [
        { value: 'person', label: 'Pin with a person' }, { value: 'tag', label: 'Pin + "You are here" tag' },
        { value: 'syrenka', label: 'Syrenka pin' }, { value: 'avatar', label: 'Round avatar' },
        { value: 'dot', label: 'Dot with halo' }, { value: 'classic', label: 'Classic blue pin' }] },
      { id: 'routeStyle', label: 'Route line style', type: 'select', default: 'dashed', options: [
        { value: 'dashed', label: 'Dashed' }, { value: 'solid', label: 'Solid' }, { value: 'dots', label: 'Dots' }] },
    ],
  },
  {
    id: 'markers', label: 'Markers',
    params: [
      { id: 'markerStyle', label: 'Marker style', type: 'select', default: 'glow', options: [
        { value: 'dot', label: 'Dot' }, { value: 'ring', label: 'Ring' }, { value: 'glow', label: 'Glow' }, { value: 'pin', label: 'Pin (big)' }] },
      { id: 'markerSize', label: 'Marker size', type: 'range', min: 0.5, max: 2, step: 0.1, default: 1 },
      { id: 'colorBy', label: 'Colour markers by', type: 'select', default: 'category', options: [
        { value: 'category', label: 'Category' }, { value: 'kind', label: 'Event / place' }, { value: 'mono', label: 'Accent colour' }] },
      // the toolbar pin button's options (data/pinGroups.js): every pin belongs to exactly one
      { id: 'pinFriends', label: 'Pins: New friends', type: 'toggle', default: true },
      { id: 'pinClubs', label: 'Pins: Social Clubs', type: 'toggle', default: true },
      { id: 'pinEvents', label: 'Pins: Events', type: 'toggle', default: true },
      { id: 'pinSights', label: 'Pins: Sights', type: 'toggle', default: true },
      { id: 'pinMusic', label: 'Pins: Music', type: 'toggle', default: true },
      { id: 'pinFood', label: 'Pins: Food & drink', type: 'toggle', default: true },
      { id: 'openNow', label: 'Pins: places open now only', type: 'toggle', default: false },
      // "In the city" layers in the same pin box (components/cityLayers.js). Toilets and AEDs only ever
      // show within 600 m of the route you're walking. Everything is on by default; switch off in the pin box
      { id: 'showToilets', label: 'Map: toilets near your route', type: 'toggle', default: true },
      { id: 'showAed', label: 'Map: defibrillators (AED) near your route', type: 'toggle', default: true },
      { id: 'showWalks', label: 'Map: walking routes', type: 'toggle', default: true },
      // toolbar "People": everyone sharing their area, as pulsing photos (components/PeopleLayer.jsx)
      { id: 'showPeople', label: 'Map: people sharing their area', type: 'toggle', default: true },
      { id: 'showEvents', label: 'Show events', type: 'toggle', default: true },
      { id: 'showPlaces', label: 'Show venues', type: 'toggle', default: true },
      { id: 'showPitches', label: 'Show open pitches', type: 'toggle', default: false },
      { id: 'showInvites', label: 'Show public invitations', type: 'toggle', default: true },
      { id: 'starredDefault', label: 'Starred places on by default', type: 'toggle', default: true },
      { id: 'timeWindow', label: 'Time window', type: 'select', default: 'month', options: [
        { value: 'today', label: 'Today' }, { value: 'weekend', label: 'Weekend' }, { value: 'week', label: 'Week' }, { value: 'month', label: 'Month' }] },
    ],
  },
  {
    id: 'mapbox', label: 'Map info boxes',
    params: [
      { id: 'boxStyle', label: 'Map info box design style', type: 'select', default: 'glass', options: [
        { value: 'glass', label: 'White' }, { value: 'card', label: 'Clean card' }, { value: 'paper', label: 'Paper' }, { value: 'outlined', label: 'Outlined' }, { value: 'poster', label: 'Poster first' }] },
      { id: 'boxWidth', label: 'Box width', type: 'range', min: 280, max: 420, step: 10, unit: 'px', default: 340 },
      { id: 'boxImages', label: 'Show images / posters', type: 'toggle', default: true },
      { id: 'boxDensity', label: 'Density', type: 'select', default: 'comfy', options: [{ value: 'compact', label: 'Compact' }, { value: 'comfy', label: 'Comfortable' }] },
    ],
  },
  {
    id: 'toolbar', label: 'Bottom toolbar',
    params: [
      { id: 'toolbarStyle', label: 'Toolbar style', type: 'select', default: 'pill', options: [
        { value: 'pill', label: 'Pill' }, { value: 'dock', label: 'Dock (separated)' }, { value: 'bar', label: 'Flat bar' }] },
      { id: 'toolbarLabels', label: 'Show labels', type: 'toggle', default: false },
      { id: 'toolbarScale', label: 'Toolbar scale', type: 'range', min: 0.8, max: 1.3, step: 0.05, default: 1 },
    ],
  },
  {
    id: 'branding', label: 'Branding',
    params: [
      { id: 'appTitle', label: 'App title', type: 'text', default: 'Syrenka.me' },
      { id: 'showTitle', label: 'Show title under search', type: 'toggle', default: false },
      { id: 'selectsBtn', label: 'Syrenka Poleca button', type: 'select', default: 'pill', options: [
        { value: 'pill', label: '1 · White pill' }, { value: 'ink', label: '2 · Black pill' }, { value: 'accent', label: '3 · Red pill' },
        { value: 'outline', label: '4 · Outline' }, { value: 'tint', label: '5 · Soft red tint' }, { value: 'serif', label: '6 · Serif' },
        { value: 'underline', label: '7 · Underlined' }, { value: 'arrow', label: '8 · With an arrow' }, { value: 'ticket', label: '9 · Ticket' },
        { value: 'lines', label: '10 · Divider' }] },
    ],
  },
  {
    id: 'motion', label: 'Motion',
    params: [
      { id: 'animSpeed', label: 'Animation speed', type: 'range', min: 0.4, max: 2, step: 0.1, unit: '×', default: 1 },
      { id: 'bounce', label: 'Springiness', type: 'range', min: 0, max: 0.6, step: 0.05, default: 0.3 },
      { id: 'reduceMotion', label: 'Reduce motion', type: 'toggle', default: false },
    ],
  },
  {
    id: 'dev', label: 'Dev',
    params: [
      { id: 'darkMode', label: 'Dark mode', type: 'toggle', default: false },
      { id: 'debugOverlay', label: 'Debug overlay (zoom, counts)', type: 'toggle', default: false },
      { id: 'apiBadge', label: 'Live API status (in Data sources)', type: 'toggle', default: true },
    ],
  },
]

export const PARAMS = Object.fromEntries(SECTIONS.flatMap((s) => s.params.map((p) => [p.id, p])))
export const DEFAULTS = Object.fromEntries(Object.values(PARAMS).map((p) => [p.id, p.default]))
