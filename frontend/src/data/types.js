import { translate } from '../i18n'

/**
 * Every pin's TYPE: exactly one per pin, from this fixed list (no "other").
 * Each type belongs to one GROUP (`place: true` = a kind of place, not something that happens): the pin box switches (data/pinGroups.js) or a city layer (utility, transit),
 * which turn every type in them on or off at once. Types are what search and the type label show.
 *
 * typeOf(p) decides a pin's type, in this order:
 *   1. what the pin says itself: a type picked when it was created ("+ Create event"), or the source
 *      (toilets / AED = utility, OSM restaurants = restaurant / cafe / alcohol, pitches, stations)
 *   2. its title, then its description (Polish and English keywords: RULES below, first match wins)
 *   3. its categories from the backend (BY_CATEGORY)
 * A pin none of these can place is a straggler: unclassified() lists them so they can be given a rule.
 */
export const TYPES = {
  // Sights
  museum: { label: 'Museum', emoji: '🏛️', color: '#0369a1', group: 'sights', place: true },
  gallery: { label: 'Gallery', emoji: '🖼️', color: '#0ea5e9', group: 'sights', place: true },
  theatre: { label: 'Theatre', emoji: '🎭', color: '#d946ef', group: 'sights', place: true },
  cinema: { label: 'Cinema', emoji: '🎬', color: '#f59e0b', group: 'sights', place: true },
  culture_centre: { label: 'Culture centre', emoji: '🏠', color: '#3b82f6', group: 'sights', place: true },
  library: { label: 'Library', emoji: '📚', color: '#6366f1', group: 'sights', place: true },
  venue: { label: 'Event venue', emoji: '🏢', color: '#64748b', group: 'sights', place: true },
  // Music
  concert: { label: 'Concert', emoji: '🎤', color: '#e7392b', group: 'music' },
  festival: { label: 'Festival', emoji: '🎪', color: '#ec4899', group: 'music' },
  nightlife: { label: 'Nightlife', emoji: '🪩', color: '#8b5cf6', group: 'music' },
  // Events
  exhibition: { label: 'Exhibition', emoji: '🖌️', color: '#0284c7', group: 'events' },
  performance: { label: 'Show', emoji: '🎭', color: '#c026d3', group: 'events' },
  screening: { label: 'Film screening', emoji: '🎞️', color: '#d97706', group: 'events' },
  education: { label: 'Education', emoji: '🎓', color: '#475569', group: 'events' },
  kids: { label: 'Kids & family', emoji: '🧸', color: '#fb7185', group: 'events' },
  market: { label: 'Market & fair', emoji: '🛍️', color: '#eab308', group: 'events' },
  business: { label: 'Business', emoji: '💼', color: '#334155', group: 'events' },
  community: { label: 'Community & help', emoji: '🏘️', color: '#0d9488', group: 'events' },
  charity: { label: 'Charity & volunteering', emoji: '💚', color: '#16a34a', group: 'events' },
  tour: { label: 'Walk & tour', emoji: '🚶', color: '#65a30d', group: 'events' },
  celebration: { label: 'Celebration', emoji: '🎉', color: '#f43f5e', group: 'events' },
  // Social clubs
  sports_class: { label: 'Sports class', emoji: '🏅', color: '#22c55e', group: 'clubs' },
  fitness: { label: 'Fitness', emoji: '🏋️', color: '#10b981', group: 'clubs' }, // gyms, classes, pools and saunas
  dance: { label: 'Dance', emoji: '💃', color: '#db2777', group: 'clubs' },
  mind_body: { label: 'Yoga & relaxation', emoji: '🧘', color: '#14b8a6', group: 'clubs' },
  running: { label: 'Running', emoji: '🏃', color: '#f97316', group: 'clubs' },
  pitch: { label: 'Pitch & court', emoji: '⚽', color: '#4d7c0f', group: 'clubs', place: true },
  sports_venue: { label: 'Stadium & sports hall', emoji: '🏟️', color: '#15803d', group: 'clubs', place: true },
  competition: { label: 'Sports competition', emoji: '🏆', color: '#ca8a04', group: 'clubs' },
  hobby_club: { label: 'Hobby club', emoji: '🎨', color: '#a855f7', group: 'clubs' },
  social_club: { label: 'Social club', emoji: '🗣️', color: '#059669', group: 'clubs' },
  // Food & drink
  restaurant: { label: 'Restaurant', emoji: '🍽️', color: '#ea580c', group: 'food', place: true },
  cafe: { label: 'Café', emoji: '☕', color: '#92400e', group: 'food', place: true },
  alcohol: { label: 'Alcohol', emoji: '🍺', color: '#b45309', group: 'food', place: true },
  // City layers (their own switches in the pin box)
  utility: { label: 'Utility', emoji: '🚻', color: '#2b6be7', group: 'utility', place: true },
  station: { label: 'Station', emoji: '🚇', color: '#1d4ed8', group: 'transit', place: true },
}

export const typeLabel = (id) => (TYPES[id] ? translate(TYPES[id].label) : '')
export const typeColor = (id) => TYPES[id]?.color || '#64748b'
export const typeGroup = (id) => TYPES[id]?.group

/** Types to pick from in search: everything but the city layers; Events mode only the ones that happen. */
export const SEARCH_TYPES = Object.keys(TYPES).filter((id) => !['utility', 'station'].includes(id))
export const EVENT_TYPE_IDS = SEARCH_TYPES.filter((id) => !TYPES[id].place)

// "+ Create event" choices (backend/app/userevents EVENT_TYPES) -> type
const FROM_EVENT_TYPE = {
  club: 'nightlife', party: 'nightlife', concert: 'concert', run: 'running', sport: 'sports_class',
  studying: 'social_club', theatre: 'performance', film: 'screening', exhibition: 'exhibition',
  picnic: 'social_club', meetup: 'social_club', games: 'social_club', yoga: 'mind_body',
}

// OpenStreetMap restaurants source: its lead starts with the amenity ("Restaurant · pizza", "Pub", "Cafe")
const FROM_EATERY = [[/^(bar|pub|biergarten)\b/i, 'alcohol'], [/^cafe\b/i, 'cafe'], [/^(restaurant|food court)\b/i, 'restaurant']]

/**
 * Title + description keywords, first match wins (Polish stems match their endings: "warsztat" ->
 * warsztaty, warsztatów). Order matters: specific before general (sauna before film, festival before concert).
 */
// JavaScript's \b treats ś, ż, ł, ó … as non-letters, so "\bświęt" would never match: every \b in the
// rules below becomes a Unicode-aware word start (before a letter) or end (after one).
const LETTER = '[\\p{L}\\p{N}]'
const unicodeWords = (re) => new RegExp(re.source.replace(/\\b/g, (_, i, src) => (i === 0 || '|(['.includes(src[i - 1]) ? `(?<!${LETTER})` : `(?!${LETTER})`)), 'iu')

const RULES = [
  // places by name (OpenStreetMap venues come without their tag)
  ['museum', /\bmuzeum|\bmuseum\b|\bcentrum nauki|\bcentrum pieniądza|\bkopernik|\bplanetarium|\bhistori|\bfotoplastikon|\bpamięci\b|\bmauzoleum/i, 'place'],
  ['gallery', /\bgaleri|\bgallery\b|\bzachęta|\bczytelnia sztuki|\batelier|\bpracowni/i, 'place'],
  ['cinema', /\bkino\b|\bkina\b|\bcinema|\bmultikino|\bhelios|\bkinoteka|\bmuranów\b|\bdomek filmowy/i, 'place'],
  ['theatre', /\bteatr|\btheat|\bamfiteatr|\bopera\b|\bfilharmoni|\bscena\b/i, 'place'],
  ['library', /\bbibliotek|\blibrary/i, 'place'],
  ['culture_centre', /\bkultur|\bdk\b|\bcentrum sztuki|\bart(s)? cent|\binstytut|\bforum\b|\bstrefa\b|\bmłodzieżow|\bfort\b|\bdworek|\bdom sztuki/i, 'place'],
  ['sports_venue', /\bstadion|\bhala\b|\barena\b|\bpływalni|\bbasen|\btor\b|\blodowisk|\bośrodek sportu|\bosir\b|\bsport/i, 'place'],
  ['nightlife', /\bklub\b|\bclub\b|\bdisco|\bdyskotek/i, 'place'],
  ['venue', /\bcentrum|\bconference|\bkonferenc|\bexpo\b|\bsala\b|\bpawilon|\bhub\b|\bbankiet|\bcatering|\bevents?\b/i, 'place'],

  // events and classes by what happens
  ['education', /\btrening pamięci|\bpamięci i koncentr|\bprogram rozwoju|\brozwoju osobist/i],
  ['screening', /\bmaraton[a-ząęó]* film/i], // a film marathon is a screening, not a race
  ['fitness', /\bsaun|\bbasen\b|\bbaseny|\bkąpiel|\baqua park|\bsiłowni|\bspinning|\bgym\b/i],
  ['festival', /\bfestiwal|\bfestival|\bfest\b|\bprzegląd\b/i],
  ['competition', /\bzawod|\bturniej|\bmistrzostw|\bgrand prix|\bliga\b|\bmecz\b|\bcup\b|\bpuchar|\bregat|\bmaraton|\bpółmaraton/i],
  ['running', /\bbieg|\brun\b|\brunning|\bparkrun|\bnordic/i],
  ['charity', /\bkrwi|\bkrwiodaw|\bcharyt|\bwolontar|\bzbiórk|\bprzygarnij|\bpola nadziei|\bpomóż|\bdonat|\bakcj[ai] /i],
  ['exhibition', /\bwystaw|\bwernisaż|\bekspozycj|\bexhibition|\bvernissage|\brzeźb|\binstalacj/i],
  ['screening', /\bseans filmow|\bseanse filmow|\bpokaz[a-ząęó]* film|\bfilm|\bkino\b|\bkinie\b|\bkinow|\bdokument|\bprojekcj|\bshort|\bslajdowisk/i],
  ['concert', /\bkoncert|\bconcert|\brecital|\bjazz|\bswing|\borkiestr|\bchór|\bsymfoni|\bkameraln|\btribute to|\bgig\b|\bgra na żywo|\bśpiew|\bpiosen|\bprzebój|\bprzeboj|\bretro\b/i],
  ['performance', /\bspektakl|\bprzedstawieni|\bteatr|\bkabaret|\bstand.?up|\bshow\b|\bmusical|\bbalet|\bopera\b|\bperformance|\bimprowizac|\bwieczór z |\bmonodram|\bmonolog|\bballet/i],
  ['market', /\btarg[iu]?\b|\bjarmark|\bkiermasz|\bgiełd|\bpchli|\bbazar|\bmarket|\bfair\b|\bwyprzedaż/i],
  ['celebration', /\bpiknik|\bbal\b|\bświęt|\bdni [a-ząćęłńóśźż]+|\bdzień [a-ząćęłńóśźż]+|\buroczyst|\bobchod|\bjubileusz|\bparada|\bkarnawał|\bhalloween|\bandrzejk|\bmikołaj|\bwigili|\bsylwest|\bpotańców/i],
  ['tour', /\bspacer|\bzwiedzani|\bwycieczk|\boprowadzani|\bgra miejska|\bgry miejsk|\btour\b|\bwalk\b|\bśladami|\bszlak|\bsurvival/i],
  ['business', /\bbiznes|\bbusiness|\bprzedsiębior|\bnetworking|\bstartup|\bkariera|\betat\b|\bwłasności intelekt|\bmarketing|\bdotacj|\bursynlab|\bksięgow|\bpodatk/i],
  ['mind_body', /\bjog[aię]|\byoga|\btai.?chi|\bqigong|\bpilates|\bmedytac|\bstretching|\brelaks|\bmindful|\boddech/i],
  ['sports_class', /\bjudo|\bkarate|\bsamoobron|\bboks|\bszerm|\bsiatk|\bkoszyk|\bpiłk|\bfutbol|\bfootball|\bbadminton|\btenis|\bakrobat|\bwspinacz|\brower|\bcycling|\bszach|\bsport|\bzajęcia ruchow|\bogólnorozwojow|\błyżw|\bhokej|\bunihokej|\bpływ|\bkajak|\bwioślar|\bbilard|\bkręgl|\bstrzel|\btrampolin|\bsquash|\bpadel|\bfrisbee|\brolki|\bskate|\bżagl|\btbc\b|\bboisk|\bju.?jitsu|\btaekwondo|\bkick/i],
  ['dance', /\bzumba|\btaneczn|\btaniec|\btańc|\bdance|\btango|\bmilong|\bsalsa|\bbachat|\bswing dance|\bbal(?:l)?room/i],
  ['fitness', /\baerobik|\bfitness|\bcrossfit|\btrening|\bgimnastyk|\bzdrowy kręgosłup|\baktywny senior|\bwalking|\bstep\b/i],
  ['community', /\bkonsultacj|\bdyżur|\bporad|\bwsparci|\bspecjalist|\bbezpieczna dzielnica|\bbezpieczn[aey] [a-ząćęłńóśźż]+ - |\bspotkanie informacyjne|\bobron[ay] cywiln|\bochron[ay] ludności|\bzus\b|\bops\b|\bpomoc prawn|\bprzemoc|\buzależni|\basystent|\bmentor|\banimator|\bśrodowiskow|\bporozmawiajmy|\bwybory|\brad[ay] osiedl|\bbadani|\bnapraw|\bdojrzał|\bemerytur|\bpierwszej pomocy|\bpsycholog/i],
  ['kids', /\bdzieci|\bdziecięc|\bmalucha|\bmaluch|\bprzedszkol|\brodzin|\bfamily|\bkids|\bmłodzież|\bbajk|\bbaśn|\bteatrzyk|\bnastolat|\bmilusiń|\bdobranock|\btata i ja|\bmama i ja/i],
  ['social_club', /\bpogaduch|\bkonwersacj|\brozmówk|\blanguage|\bjęzyk|\bquiz|\bplanszów|\bgry\b|\bgier\b|\bgra w |\brpg\b|\brozegrani|\bklub seniora|\bspotkanie towarzysk|\bmeetup|\bkawiarenk|\bklub dyskusyjn|\bsąsied|\bmiędzykulturow|\bseniorów z klubu|\bangielsk|\bniemieck|\bhiszpańsk|\bfrancusk|\bwłosk|\bpo polsku\b|\bczas na rozmowę/i],
  ['hobby_club', /\bdkk\b|\bklub książki|\bdyskusyjny klub|\bklub literack|\bczytelnicz|\bwarsztat|\bkreatywn|\bmalowani|\bmalarsk|\bpomaluj|\brysun|\bszkic|\bceramik|\bglin|\brękodzie|\bszyci|\bszyjemy|\bdzierga|\bna drutach|\bmakram|\bhaft|\btkack|\bfrywolit|\brecykling|\bdecoupage|\bfotograf|\bkolaż|\bplastyczn|\bkolorowani|\bkomiks|\bgrafik|\brobotyk|\blego\b|\bklock|\bmodelarsk|\bogrod|\bzielarsk|\bgrzyb|\bkulinarn|\bgotowani|\bdo dzieła|\bkodowani|\bprogramowani/i],
  ['education', /\bkonkurs|\bwykład|\bprelekcj|\bspotkanie z |\bspotkanie autorsk|\bwieczór autorsk|\bpremiera książki|\bdebat|\bpanel\b|\bkonferencj|\bszkoleni|\bkurs\b|\bkursy\b|\bseminari|\blekcj|\bnauk|\bedukac|\bhistori|\bcyberbezpiecz|\bstres|\bzdrow|\bwitalność|\bodporność|\bschudn|\bodżywia|\bmatematyk|\bnowych technolog|\bterapeut|\bo ryzykach|\btalk\b|\blecture|\bwielkie artystki|\bspotkanie poświęcone|\bspotkanie\b/i],
].map(([type, re, only]) => [type, unicodeWords(re), only])

// what the backend's categories mean when the text doesn't say (first category that maps wins)
const BY_CATEGORY = {
  music: 'concert', nightlife: 'nightlife', theatre: 'performance', film: 'screening', exhibitions: 'exhibition',
  meetups: 'social_club', grzybki: 'hobby_club', study_buddies: 'social_club', running: 'running', yoga: 'mind_body',
  sports: 'sports_class', festivals: 'festival', markets: 'market', education: 'education', family: 'kids',
  business: 'business', health: 'education', food: 'restaurant', toilets: 'utility', aed: 'utility',
}
// the same categories on a PLACE mean the venue, not the event
const PLACE_BY_CATEGORY = {
  theatre: 'theatre', film: 'cinema', exhibitions: 'gallery', culture: 'culture_centre', nightlife: 'nightlife',
  music: 'venue', business: 'venue', sports: 'sports_venue', food: 'restaurant', toilets: 'utility', aed: 'utility',
}

/** A pin's type id, or null when nothing places it (a straggler; see unclassified()). */
export function classify(p) {
  if (!p) return null
  if (TYPES[p.type]) return p.type // set by the backend
  // picked in "+ Create event": the older choices first (their "theatre" meant a play, not the building)
  if (FROM_EVENT_TYPE[p.event_type]) return FROM_EVENT_TYPE[p.event_type]
  if (TYPES[p.event_type]) return p.event_type
  const cats = p.categories || []
  if (cats.includes('toilets') || cats.includes('aed') || p.source === 'warsaw_toilets' || p.source === 'warsaw_aed') return 'utility'
  if (cats.includes('transit') || p.source === 'osm_transit') return 'station'
  if (p.source === 'warsaw_pitches') return 'pitch'
  if (p.source === 'osm_restaurants') {
    for (const [re, t] of FROM_EATERY) if (re.test(p.lead || '')) return t
    return cats.includes('nightlife') ? 'alcohol' : 'restaurant'
  }
  const place = p.kind === 'place'
  // the title first (it says what the thing is); the description only when the title says nothing
  for (const words of [`${p.title || ''} ${p.subtitle || ''}`, p.lead || '']) {
    for (const [type, re, only] of RULES) {
      if (only === 'place' ? !place : place) continue
      if (re.test(words)) return type
    }
  }
  const map = place ? PLACE_BY_CATEGORY : BY_CATEGORY
  for (const c of cats) if (map[c]) return map[c]
  return null
}

// fallback for a straggler so the map never shows a pin without a type: what kind of thing it is
const LAST_RESORT = { place: 'venue', class: 'sports_class', event: 'community' }

/** A pin's type: always one of TYPES. */
export const typeOf = (p) => classify(p) || LAST_RESORT[p?.kind] || 'community'

const SPECIFIC = new Set(['music', 'nightlife', 'theatre', 'film', 'exhibitions', 'running', 'yoga', 'festivals', 'markets', 'family', 'business', 'food', 'grzybki', 'study_buddies'])

// a type that always brings another with it, and words that add types on top of the main one
const ALSO = { dance: ['fitness'] }
const ALSO_WORDS = [
  [/\bsurvival|\bbushcraft|\bgrzyb|\bornitolog|\bfotograf/i, ['hobby_club']], // outdoor hobbies
  [/\bplastyczn|\brysun|\bmalowani|\bmalarsk|\bsztuk|\bceramik|\bgrafik|\bartyst|\bkomiks|\bilustrac/i, ['hobby_club', 'education']], // art
  [/\bnapraw|\brękodzie|\bszyci|\bszyjemy|\bwarsztat|\bmakram|\bhaft|\bdzierga|\brecykling/i, ['hobby_club']], // making and mending
].map(([re, types]) => [unicodeWords(re), types])

/**
 * Every type a pin counts as: its main type first (the badge and the label), then the others its title
 * also names (a family table-tennis tournament: competition, sports class, kids), the "also" rules above
 * (tango: dance + fitness; a painting class: hobby + education), then its specific backend categories.
 * Search and the type switches use these, so a pin shows under each of its types.
 */
export function typesOf(p) {
  const out = [typeOf(p)]
  if (!p) return out
  const add = (t) => { if (t && TYPES[t] && !out.includes(t) && !['utility', 'station'].includes(t)) out.push(t) }
  const place = p.kind === 'place'
  const title = `${p.title || ''} ${p.subtitle || ''}`
  for (const [type, re, only] of RULES) if ((only === 'place') === place && re.test(title)) add(type)
  for (const t of ALSO[out[0]] || []) add(t)
  for (const [re, types] of ALSO_WORDS) if (re.test(title)) types.forEach(add)
  // only the backend's specific categories: the broad ones (meetups, health, culture, sports, education) say too little
  for (const c of p.categories || []) if (SPECIFIC.has(c)) { add(BY_CATEGORY[c]); if (place) add(PLACE_BY_CATEGORY[c]) }
  return out
}

/** Pins nothing in the rules places (for checking the rules; ideally empty). */
export const unclassified = (features) => (features || []).filter((f) => !classify(f.properties))
