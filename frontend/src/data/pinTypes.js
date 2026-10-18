/**
 * What a pin *is* (cinema, bank, school, concert, pitch …): an emoji and a colour per type, drawn as a
 * small round badge on the map (MapView's `wl-icons` layer). The API has no single "type" field, so it is
 * worked out from what a pin does carry: Kamil's OSM venue_type when there is one, a few unmistakable
 * words in the name ("Kino …", "Bank …", "Liceum …"), then the first meaningful category.
 */

export const PIN_TYPES = {
  invite: { emoji: '🤝', color: '#0fa37f', label: 'Invitation' },
  cinema: { emoji: '🎬', color: '#f59e0b', label: 'Cinema' },
  theatre: { emoji: '🎭', color: '#d946ef', label: 'Theatre' },
  museum: { emoji: '🏛️', color: '#0369a1', label: 'Museum' },
  gallery: { emoji: '🖼️', color: '#0ea5e9', label: 'Gallery' },
  music: { emoji: '🎵', color: '#e7392b', label: 'Music' },
  club: { emoji: '🪩', color: '#8b5cf6', label: 'Club' },
  bar: { emoji: '🍺', color: '#b45309', label: 'Bar & pub' },
  cafe: { emoji: '☕', color: '#92400e', label: 'Café' },
  food: { emoji: '🍴', color: '#ea580c', label: 'Restaurant' },
  market: { emoji: '🧺', color: '#eab308', label: 'Market' },
  pool: { emoji: '🏊', color: '#0891b2', label: 'Swimming pool' },
  running: { emoji: '🏃', color: '#f97316', label: 'Running' },
  yoga: { emoji: '🧘', color: '#14b8a6', label: 'Yoga' },
  gym: { emoji: '🏋️', color: '#16a34a', label: 'Gym' },
  sport: { emoji: '⚽', color: '#22c55e', label: 'Sport' },
  bank: { emoji: '🏦', color: '#475569', label: 'Bank' },
  school: { emoji: '🎓', color: '#64748b', label: 'School' },
  library: { emoji: '📚', color: '#6366f1', label: 'Library' },
  study: { emoji: '📖', color: '#4f46e5', label: 'Study buddies' },
  church: { emoji: '⛪', color: '#7c3aed', label: 'Church' },
  park: { emoji: '🌳', color: '#15803d', label: 'Park' },
  mushrooms: { emoji: '🍄', color: '#a16207', label: 'Grzybki' },
  festival: { emoji: '🎉', color: '#ec4899', label: 'Festival' },
  family: { emoji: '🧸', color: '#fb7185', label: 'Family & kids' },
  health: { emoji: '🩺', color: '#06b6d4', label: 'Health' },
  business: { emoji: '💼', color: '#334155', label: 'Business' },
  meetup: { emoji: '👋', color: '#10b981', label: 'Meetup' },
  culture: { emoji: '🎨', color: '#3b82f6', label: 'Culture' },
  other: { emoji: '📍', color: '#9ca3af', label: 'Other' },
}

// Kamil's OpenStreetMap venues (osm_restaurants …)
const VENUE_TYPES = {
  restaurant: 'food', fast_food: 'food', food_court: 'food', ice_cream: 'cafe', cafe: 'cafe',
  bar: 'bar', pub: 'bar', biergarten: 'bar', nightclub: 'club', cinema: 'cinema', theatre: 'theatre',
  museum: 'museum', gallery: 'gallery', arts_centre: 'culture', library: 'library', pitch: 'sport',
  sports_centre: 'gym', fitness_centre: 'gym', swimming_pool: 'pool', bank: 'bank', school: 'school',
  university: 'school', college: 'school', place_of_worship: 'church', park: 'park', marketplace: 'market',
}

// words in the name that say what a place is, whatever its category says (Polish and English). Each
// matches at the start of a word; "$" marks the end of one ("targ$" is a market, "Targówek" is not).
// (\b would not do: JavaScript counts ó, ł, ś … as non-letters.)
const word = (alts) => new RegExp(`(?<!\\p{L})(?:${alts.replace(/\$/g, '(?!\\p{L})')})`, 'iu')
const NAME_WORDS = [
  [word('kino|kina$|cinema|multikino|iluzjon'), 'cinema'],
  [word('bank$|banku$'), 'bank'],
  [word('basen|pływalni|aquapark'), 'pool'],
  [word('siłowni|fitness|crossfit'), 'gym'],
  [word('muzeum|museum'), 'museum'],
  [word('galeria|gallery|zachęta'), 'gallery'],
  [word('bibliote[kc]|library'), 'library'],
  [word('teatr|theatre|opera$|filharmoni'), 'theatre'],
  [word('kościół|kościoł|parafi|bazylik|katedr|cerkiew|synagog'), 'church'],
  [word('kawiarni|café|cafe$|coffee'), 'cafe'],
  [word('restauracj|bistro|pizzeri|bar mleczny'), 'food'],
  [word('pub$|piwiarni|browar'), 'bar'],
  [word('targ$|targi$|bazar|hala mirowska|jarmark'), 'market'],
  [word('bieg$|biegi$|biegow|bieżni|nordic walking|parkrun'), 'running'],
  [word('joga|jogi$|yoga|pilates'), 'yoga'],
  [word('grzyb'), 'mushrooms'],
]
const SCHOOL = word('szkoł|szkol|liceum|gimnazjum|przedszkol|uniwersytet|politechnik|university|school')

// first category that says something, in this order
const CATEGORIES = [
  ['film', 'cinema'], ['theatre', 'theatre'], ['music', 'music'], ['nightlife', 'club'], ['exhibitions', 'gallery'],
  ['markets', 'market'], ['food', 'food'], ['running', 'running'], ['yoga', 'yoga'], ['sports', 'sport'],
  ['study_buddies', 'study'], ['grzybki', 'mushrooms'], ['festivals', 'festival'], ['family', 'family'],
  ['education', 'school'], ['health', 'health'], ['business', 'business'], ['meetups', 'meetup'], ['culture', 'culture'],
]

export function pinType(p) {
  if (p.source === 'syrenka-users' || p.is_public_invite) return 'invite'
  if (VENUE_TYPES[p.venue_type]) return VENUE_TYPES[p.venue_type]
  const cats = p.categories || []
  const name = [p.title, p.venue_name].filter(Boolean).join(' · ')
  for (const [re, type] of NAME_WORDS) if (re.test(name)) return type
  // a school's name on a pitch / running track ("Boisko – Liceum nr …") is just where the sport happens
  if (SCHOOL.test(name) && !cats.some((c) => ['sports', 'running', 'yoga'].includes(c))) return 'school'
  for (const [cat, type] of CATEGORIES) if (cats.includes(cat)) return type
  return 'other'
}

export const pinTypeOf = (p) => PIN_TYPES[pinType(p)]
