/**
 * Reads a typed search the way a person means it: "nightlife in Śródmieście next Saturday",
 * "koncerty na Saskiej Kępie w weekend", "jazz tonight". Polish or English, with or without accents.
 *
 *   what  -> category slugs (with synonyms: club, bar, impreza, koncert, kino, wystawa, ...)
 *   when  -> { from, to } local days (+ evening), from today / tomorrow / weekend / weekdays / "next ..."
 *   where -> an area from public/warsaw_areas.geojson (districts and neighbourhoods, inflected forms too)
 *   terms -> whatever is left, minus filler words ("in", "next", "w", "na", "coś", ...)
 */
import { CATEGORIES } from '../data/categories'
import { translate } from '../i18n'
import { fold } from './areas'

// folded (lowercase, no accents) synonyms per category, on top of each category's English and Polish label
const SYNONYMS = {
  nightlife: ['nightlife', 'night life', 'nightclub', 'nightclubs', 'club', 'clubs', 'clubbing', 'party', 'parties', 'rave', 'disco', 'dj', 'techno', 'bar', 'bars', 'pub', 'pubs', 'drinks', 'cocktails',
    'klub', 'kluby', 'klubie', 'klubach', 'impreza', 'imprezy', 'impreze', 'imprezka', 'imprezki', 'zycie nocne', 'zycia nocnego', 'dyskoteka', 'bary', 'barze', 'puby', 'koktajle', 'na miasto'],
  music: ['music', 'concert', 'concerts', 'gig', 'gigs', 'live music', 'jazz', 'rock', 'opera', 'philharmonic', 'recital',
    'muzyka', 'muzyki', 'koncert', 'koncerty', 'koncertu', 'koncercie', 'filharmonia', 'filharmonii'],
  theatre: ['theatre', 'theater', 'play', 'plays', 'stand up', 'standup', 'comedy', 'cabaret', 'teatr', 'teatru', 'teatrze', 'spektakl', 'spektakle', 'kabaret', 'przedstawienie'],
  film: ['film', 'films', 'movie', 'movies', 'cinema', 'screening', 'kino', 'kina', 'kinie', 'seans', 'filmy'],
  exhibitions: ['exhibition', 'exhibitions', 'museum', 'museums', 'gallery', 'galleries', 'art', 'vernissage',
    'wystawa', 'wystawy', 'wystawe', 'muzeum', 'muzea', 'galeria', 'galerii', 'sztuka', 'wernisaz'],
  meetups: ['meetup', 'meetups', 'meet up', 'networking', 'language exchange', 'spotkanie', 'spotkania', 'wymiana jezykowa'],
  running: ['run', 'runs', 'running', 'jogging', 'parkrun', 'bieganie', 'bieg', 'biegi', 'biegac'],
  yoga: ['yoga', 'joga', 'jogi', 'jodze'],
  sports: ['sport', 'sports', 'football', 'basketball', 'volleyball', 'gym', 'swimming', 'pool', 'tennis', 'fitness', 'workout',
    'pilka', 'pilka nozna', 'koszykowka', 'siatkowka', 'silownia', 'plywanie', 'basen', 'tenis', 'trening'],
  festivals: ['festival', 'festivals', 'fest', 'festiwal', 'festiwale', 'festiwalu'],
  markets: ['market', 'markets', 'flea market', 'fair', 'targ', 'targi', 'jarmark', 'bazar', 'pchli targ'],
  culture: ['culture', 'cultural', 'kultura', 'kulturalne'],
  education: ['education', 'lecture', 'lectures', 'workshop', 'workshops', 'course', 'class', 'warsztaty', 'wyklad', 'wyklady', 'kurs', 'zajecia'],
  family: ['family', 'kids', 'children', 'for kids', 'dzieci', 'dla dzieci', 'rodzina', 'rodzinne', 'rodzinny'],
  business: ['business', 'startup', 'biznes'],
  health: ['health', 'zdrowie', 'medical'],
  grzybki: ['grzybki', 'mushrooms', 'mushroom picking', 'grzyby'],
  study_buddies: ['study', 'studying', 'study buddies', 'wspolna nauka', 'nauka'],
}

// specific words that pick a category but should also rank the items that mention them ("jazz" within music)
const KEEP_AS_TERM = new Set(['jazz', 'rock', 'techno', 'opera', 'recital', 'parkrun', 'stand up', 'standup', 'kabaret', 'cabaret', 'rave', 'disco', 'dj', 'pub', 'pubs'])

const STOP = new Set(('in at on the a an for near nearby this next coming upcoming what whats is are to do go going me my i with and or of any some ' +
  'something things thing events event happening around best good nice cool find show where when there that please ' +
  'w we na do z ze o co cos jest sa gdzie kiedy przy obok kolo blisko ten ta te to tym tej tego najblizszy najblizsza najblizsze najblizszej ' +
  'nastepny nastepna nastepne nastepnej przyszly przyszla przyszle przyszlej ciekawe ciekawego fajne fajnego dzieje sie robic gdzies ' +
  'wydarzenia wydarzenie wydarzen jakies jakis jakas mozna idziemy isc pojsc chce chcialbym chcialabym szukam').split(' '))

const NEXT = new Set(['next', 'following', 'nastepny', 'nastepna', 'nastepne', 'nastepnej', 'przyszly', 'przyszla', 'przyszle', 'przyszlej', 'kolejny', 'kolejna'])
const DAYS = [
  ['sunday', 'sun', 'niedziela', 'niedziele', 'niedzieli', 'niedziel'],
  ['monday', 'mon', 'poniedzialek', 'poniedzialku'],
  ['tuesday', 'tue', 'wtorek', 'wtorku'],
  ['wednesday', 'wed', 'sroda', 'srode', 'srody', 'srodzie'],
  ['thursday', 'thu', 'czwartek', 'czwartku'],
  ['friday', 'fri', 'piatek', 'piatku'],
  ['saturday', 'sat', 'sobota', 'sobote', 'soboty', 'sobocie'],
]
const TODAY = ['today', 'tonight', 'dzis', 'dzisiaj', 'dzisiejszy', 'dzisiejsza']
const TOMORROW = ['tomorrow', 'jutro', 'jutrzejszy', 'jutrzejsza']
const WEEKEND = ['weekend', 'weekendzie', 'weekendu', 'weekendy']
const WEEK = ['week', 'tydzien', 'tygodniu', 'tygodnia']
const MONTH = ['month', 'miesiac', 'miesiacu', 'miesiaca']
const EVENING = ['tonight', 'evening', 'night', 'late', 'wieczor', 'wieczorem', 'wieczorny', 'wieczorna', 'noc', 'noca', 'nocy', 'nocne']

const day = (base, offset) => { const d = new Date(base); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + offset); return d }

let synonymIndex = null
/** [phrase tokens, slug], longest phrases first, so "zycie nocne" wins over "nocne". */
function synonyms() {
  if (!synonymIndex) {
    const list = []
    for (const slug of Object.keys(CATEGORIES)) {
      const phrases = new Set([...(SYNONYMS[slug] || []), fold(CATEGORIES[slug].label), fold(translate(CATEGORIES[slug].label))])
      for (const ph of phrases) if (ph) list.push([ph.split(' '), slug])
    }
    synonymIndex = list.sort((a, b) => b[0].length - a[0].length)
  }
  return synonymIndex
}

// does a typed word mean this name word? exact, or a Polish case ending: woli~wola, kepie~kepa, mokotowie~mokotow
function sameWord(typed, name) {
  if (typed === name) return true
  if (typed.length < 3 || STOP.has(typed)) return false
  let k = 0
  while (k < typed.length && k < name.length && typed[k] === name[k]) k++
  return k >= Math.max(3, name.length - 2) && Math.abs(typed.length - name.length) <= 4
}

/** Parse a query. areas: from loadAreas() (may be empty). Returns { categories, when, evening, area, terms }. */
export function understand(query, areas = [], now = new Date()) {
  const tokens = fold(query).split(' ').filter(Boolean)
  const used = new Array(tokens.length).fill(false)
  const take = (i, n) => { for (let k = i; k < i + n; k++) used[k] = true }

  // what
  const categories = [], keep = []
  for (const [phrase, slug] of synonyms()) {
    for (let i = 0; i + phrase.length <= tokens.length; i++) {
      if (used.slice(i, i + phrase.length).some(Boolean)) continue
      if (phrase.every((w, k) => tokens[i + k] === w)) {
        take(i, phrase.length)
        if (!categories.includes(slug)) categories.push(slug)
        if (KEEP_AS_TERM.has(phrase.join(' '))) keep.push(phrase.join(' '))
      }
    }
  }

  // where: the longest area name whose words all appear in a row (any Polish case ending)
  let area = null, areaLen = 0
  for (const a of areas) {
    const n = a.tokens.length
    if (n < areaLen) continue
    for (let i = 0; i + n <= tokens.length; i++) {
      if (used.slice(i, i + n).some(Boolean)) continue
      if (a.tokens.every((w, k) => sameWord(tokens[i + k], w)) && (n > areaLen || (a.kind === 'district' && area?.kind !== 'district'))) {
        area = { ...a, at: i }; areaLen = n
      }
    }
  }
  if (area) take(area.at, areaLen)

  // when
  let when = null
  const has = (list) => tokens.findIndex((tok, i) => !used[i] && list.includes(tok))
  const isNext = tokens.some((tok, i) => !used[i] && NEXT.has(tok))
  const dow = now.getDay()
  let i
  if ((i = has(TODAY)) >= 0) { used[i] = true; when = { from: day(now, 0), to: day(now, 0), key: 'today' } }
  else if ((i = has(TOMORROW)) >= 0) { used[i] = true; when = { from: day(now, 1), to: day(now, 1), key: 'tomorrow' } }
  else if ((i = has(WEEKEND)) >= 0) {
    used[i] = true
    const toSat = dow === 0 ? -1 : 6 - dow // Sunday: this weekend is today
    const start = isNext ? (dow === 0 ? 6 : toSat + 7) : Math.max(0, toSat)
    when = { from: day(now, start), to: day(now, isNext ? start + 1 : dow === 0 ? 0 : toSat + 1), key: 'weekend' }
  } else if ((i = has(WEEK)) >= 0) { used[i] = true; when = isNext ? { from: day(now, 7 - ((dow + 6) % 7)), to: day(now, 13 - ((dow + 6) % 7)), key: 'week' } : { from: day(now, 0), to: day(now, 6), key: 'week' } }
  else if ((i = has(MONTH)) >= 0) { used[i] = true; when = { from: day(now, 0), to: day(now, 30), key: 'month' } }
  else {
    for (let d = 0; d < 7 && !when; d++) {
      const j = has(DAYS[d])
      if (j < 0) continue
      used[j] = true
      let ahead = (d - dow + 7) % 7
      if (ahead === 0 && isNext) ahead = 7
      when = { from: day(now, ahead), to: day(now, ahead), key: 'day' }
    }
  }
  let evening = categories.includes('nightlife') || tokens.includes('tonight')
  tokens.forEach((tok, k) => { if (!used[k] && EVENING.includes(tok)) { used[k] = true; evening = true; if (!when && (tok === 'tonight')) when = { from: day(now, 0), to: day(now, 0), key: 'today' } } })

  const terms = [...keep, ...tokens.filter((tok, k) => !used[k] && !STOP.has(tok) && !NEXT.has(tok) && tok.length > 1)]
  return { categories, when, evening, area: area ? { name: area.name, kind: area.kind, district: area.district, bbox: area.bbox, feature: area.feature, ref: area } : null, terms }
}
