import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from './config/store'
import { useLang } from './i18n'
import { fetchBusyAreas, fetchCityLayer, fetchFeatures, locateByIp, routeTo, runSearch, WARSAW_CENTER } from './data/api'
import { alongPaths, CITY_LAYERS, walkBoxFeature, walkPaths } from './components/cityLayers'
import { useFavourites } from './hooks/useFavourites'
import { useScrollFade } from './hooks/useScrollFade'
import { useStartPoint } from './hooks/useStartPoint'
import { useIsMobile } from './hooks/useMedia'
import { curate } from './mapboxes/curate'
import { BottomSheet } from './components/BottomSheet'
import { BottomToolbar } from './components/BottomToolbar'
import { PeopleLayer } from './components/PeopleLayer'
import { InterfaceEditor } from './components/InterfaceEditor'
import { DEV_TOOLS } from './config/env'
import { Mermaid } from './components/Icons'
import { MapBox } from './components/MapBox'
import { countPinGroups, MapView } from './components/MapView'
import { ResultsList, SearchBar } from './components/SearchBar'
import { FavouritesPanel, MessagesPanel, ProfilePanel, SettingsPanel, SlideOver } from './components/SidePanels'
import { AuthLinks } from './components/Account'
import { startChatSocket, useMyChats } from './data/chat'
import { SelectsRail } from './components/SelectsRail'
import { Landing } from './components/Landing'
import { flySearch } from './landing/searchFlight'
import { CreateEventPanel } from './components/CreateEventPanel'
import { AccountButton } from './components/AccountButton'
import { ConditionsChip } from './components/ConditionsChip'
import { AUDIENCES } from './data/categories'
import { landingSearch, windowFor } from './landing/search'
import { smartSearch } from './search/engine'
import { upcoming } from './data/api'

/** Map controls arrive part by part after the start page, never all at once. */
const Stage = ({ delay = 0, children }) => (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay, duration: 0.45 } }} exit={{ opacity: 0, transition: { duration: 0.25 } }}>{children}</motion.div>
)

/** Where an element sits on screen right now (null when it isn't rendered). */
const rectOf = (selector) => document.querySelector(selector)?.getBoundingClientRect() ?? null

const MAX_OPEN_BOXES = 20 // older boxes stay open and scroll; only past this many does the oldest close

export default function App() {
  const { values, set } = useConfig()
  const spring = useSpring()
  const { lang, t } = useLang()
  const mobile = useIsMobile()
  const mapRef = useRef(null)
  const getMap = useCallback(() => mapRef.current?.getMap(), []) // stable: the start page's network visual keeps its timers across renders
  const fav = useFavourites()

  const [features, setFeatures] = useState(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [favOnly, setFavOnly] = useState(false)
  const [panel, setPanel] = useState(null)
  const [panelFull, setPanelFull] = useState(false) // desktop mode 3: the slide-over fills the screen
  const [person, setPerson] = useState(null) // { id } of someone tapped on the map: their profile in the slide-over
  const [eventChat, setEventChat] = useState(null) // the event chat open in Messages: { kind: 'event' | 'userevent', id }
  const myChats = useMyChats()
  useEffect(() => startChatSocket(), []) // live chat messages while logged in (data/chat.js)
  const [view, setView] = useState('landing') // every visit starts on the start page ("Search")
  const [flying, setFlying] = useState(false) // the search pill is in flight between the start page and the map
  const [revealed, setRevealed] = useState(false) // pins and areas shown: only once the pill has landed on the map
  const flight = useRef(null) // { from: DOMRect, text, after } for the next view change
  const [entryQuery, setEntryQuery] = useState('')
  const [boxes, setBoxes] = useState([]) // [{ key, feature, data, expanded }]
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [sheet, setSheet] = useState(null) // mobile: 'results' | 'box' | null
  const [zoom, setZoom] = useState(11.6)
  const [toast, setToast] = useState(null)
  const [busyAreas, setBusyAreas] = useState(null)
  const [me, setMe] = useState(null)
  const start = useStartPoint() // picked in Profile; beats the IP guess
  const firstPosition = useRef(true)
  const [route, setRoute] = useState(null)
  // "In the city" layers (toilets, AED, walking routes): fetched the first time each is switched on.
  // Toilets and AEDs only show along the walk you're on: within 600 m of the route (cityLayers.alongPaths).
  const [city, setCity] = useState({})
  const paths = useMemo(() => walkPaths(route, boxes), [route, boxes])
  const onPath = paths.length > 0
  useEffect(() => {
    // toilets / AEDs wait for a route (or Settings, which counts them); walking routes and stations load straight away
    const need = (l) => l.id === 'walks' || l.id === 'transit' || onPath || panel === 'settings'
    for (const l of CITY_LAYERS) if (values[l.param] && !city[l.id] && need(l)) fetchCityLayer(l.id).then((fc) => setCity((c) => ({ ...c, [l.id]: fc })))
  }, [values.showToilets, values.showAed, values.showWalks, values.showStations, onPath, panel]) // eslint-disable-line react-hooks/exhaustive-deps
  const cityShown = useMemo(() => alongPaths(city, paths), [city, paths])
  const cityCounts = Object.fromEntries(CITY_LAYERS.map((l) => [l.id, city[l.id]?.features.length])) // Settings -> Data sources
  const [draftPin, setDraftPin] = useState(null) // "+ Create event" is open: where the new event happens
  const meRef = useRef(null)
  useEffect(() => { meRef.current = me }, [me])
  const [chat, setChat] = useState(() => { try { return JSON.parse(localStorage.getItem('warszawa-live.chat.v1') || '[]') } catch { return [] } })
  useEffect(() => { localStorage.setItem('warszawa-live.chat.v1', JSON.stringify(chat.map((m) => ({ ...m, results: undefined })))) }, [chat])

  useEffect(() => {
    fetchFeatures().then(setFeatures); fetchBusyAreas().then(setBusyAreas)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // Position: the starting point picked in Profile, otherwise an IP guess re-polled every 5 minutes
  // (the IP changes when the user moves networks)
  useEffect(() => {
    const first = firstPosition.current
    firstPosition.current = false
    if (start) {
      setMe(start.lngLat)
      if (!first) {
        const m = mapRef.current?.getMap()
        m?.flyTo({ center: start.lngLat, zoom: Math.max(m.getZoom(), 14), duration: 1100, essential: true })
        say(t('Starting point · {label}', { label: start.label }))
      }
      return
    }
    locateByIp().then((loc) => { setMe(loc.lngLat); say(t(first ? 'Approximate location from your IP · set yours in Profile' : 'Using your approximate IP location')) })
    const poll = setInterval(() => locateByIp().then((loc) => setMe(loc.lngLat)), 5 * 60 * 1000)
    return () => clearInterval(poll)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start])
  const featureList = features?.features || []

  const say = useCallback((t) => { setToast(t); setTimeout(() => setToast(null), 1800) }, [])

  // ---------- map boxes ----------
  // Open boxes stay open: the stack scrolls (soft top / bottom edges, scrollbar only while scrolling)
  const boxesRef = useScrollFade()
  const openBox = useCallback(async (feature, { fly = true } = {}) => {
    const key = String(feature.properties.event_id)
    const data = curate(feature)
    setBoxes((b) => {
      const rest = b.filter((x) => x.key !== key).map((x) => ({ ...x, expanded: false }))
      return [{ key, feature, data, expanded: false }, ...rest].slice(0, mobile ? 1 : MAX_OPEN_BOXES) // phones: one event at a time
    })
    boxesRef.current?.scrollTo({ top: 0, behavior: 'smooth' }) // the newest box goes on top: bring it into view
    if (mobile) setSheet('box')
    if (fly) mapRef.current?.flyTo(feature, 14.5)
    const from = meRef.current
    if (from) {
      setBoxes((b) => b.map((x) => (x.key === key ? { ...x, journey: { pending: true } } : x)))
      routeTo(from, feature.geometry.coordinates).then((j) => {
        setBoxes((b) => b.map((x) => (x.key === key ? { ...x, journey: j } : x)))
        setRoute({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: j.geometry, properties: {} }] })
      })
    }
  }, [mobile]) // eslint-disable-line react-hooks/exhaustive-deps

  // events in the new language after a PL/EN switch (the server sends Claude's translations)
  const firstLang = useRef(true)
  useEffect(() => {
    if (firstLang.current) { firstLang.current = false; return }
    fetchFeatures().then((fc) => {
      setFeatures(fc)
      // open boxes swap to the same event in the new language
      const byId = new Map(fc.features.map((f) => [String(f.properties.event_id), f]))
      setBoxes((b) => b.map((x) => { const f = byId.get(x.key); return f ? { ...x, feature: f, data: curate(f) } : x }))
    })
  }, [lang])

  // re-curate open boxes so their text follows a language switch
  useEffect(() => {
    setBoxes((b) => b.map((x) => ({ ...x, data: curate(x.feature) })))
  }, [lang])

  // a walking route: its box (journey to the first stop) and the whole line in view
  const pickWalk = (route) => {
    openBox(walkBoxFeature(route), { fly: false })
    const b = route.geometry.coordinates.reduce((acc, [x, y]) => [Math.min(acc[0], x), Math.min(acc[1], y), Math.max(acc[2], x), Math.max(acc[3], y)], [999, 999, -999, -999])
    mapRef.current?.getMap()?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mobile ? { top: 120, bottom: window.innerHeight * 0.5, left: 30, right: 30 } : { top: 110, bottom: 110, left: 80, right: 420 }, maxZoom: 15.5, duration: 900 })
  }
  const closeBox = (key) => setBoxes((b) => { const n = b.filter((x) => x.key !== key); if (!n.length) setRoute(null); return n })
  const closeAll = () => { setBoxes([]); setResults(null); setRoute(null); if (sheet) setSheet(null); say(t('Closed all map boxes')) }
  const expandBox = (key) => setBoxes((b) => b.map((x) => ({ ...x, expanded: x.key === key ? !x.expanded : false })))
  const selectedId = boxes[0]?.key
  const pinCounts = useMemo(() => countPinGroups(featureList, values, fav.ids, favOnly), [featureList, values, fav.ids, favOnly])

  // ---------- search ----------
  const onSearch = async (mode, q, opts) => {
    if (mode === 'events' && (opts?.when || opts?.where)) { // Events dropdown: tag · when · where
      if (opts.when) set('timeWindow', windowFor(opts.when))
      showSearch(await smartSearch(opts.category || opts.type ? '' : q.split(' · ')[0], upcoming(featureList), { mode: 'events', category: opts.category, type: opts.type, when: opts.when, where: opts.where }), mode, opts.where)
      return
    }
    if (!q.trim() && mode !== 'assistant') { setResults(null); return }
    setSearching(true)
    if (mode === 'assistant') setChat((c) => [...c, { role: 'user', text: q }])
    const r = await runSearch(mode, q, featureList, opts)
    setSearching(false)
    if (mode === 'assistant') { setChat((c) => [...c, { role: 'assistant', text: r.answer, results: r.results }]); if (r.results?.length && r.results.length <= 40) fitResults(r.results); return }
    if (r.understood?.when) set('timeWindow', windowFor(r.understood.when))
    showSearch(r, mode)
  }
  // results list + the map: the searched area outlined and in view, else the matches in view
  const showSearch = (r, mode, where) => {
    setResults({ mode, q: r.summary, results: r.results, exact: r.exact, area: r.area })
    if (mobile) setSheet('results')
    if (r.area) fitArea(r.area)
    else if (r.results.length) fitResults(r.results)
    else if (where?.lngLat) mapRef.current?.getMap()?.flyTo({ center: where.lngLat, zoom: 15, duration: 1100 })
  }
  const fitArea = (area) => {
    const ring = (area.geometry.type === 'Polygon' ? [area.geometry.coordinates] : area.geometry.coordinates).flatMap((poly) => poly[0])
    const b = ring.reduce((acc, [x, y]) => [Math.min(acc[0], x), Math.min(acc[1], y), Math.max(acc[2], x), Math.max(acc[3], y)], [999, 999, -999, -999])
    mapRef.current?.getMap()?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mobile ? { top: 100, bottom: window.innerHeight * 0.5, left: 30, right: 30 } : { top: 100, bottom: 100, left: 620, right: 380 }, maxZoom: 15.5, duration: 900 })
  }
  const fitResults = (list) => {
    const pts = list.slice(0, 40).map((f) => f.geometry?.coordinates).filter(Boolean)
    if (!pts.length) return
    const m = mapRef.current?.getMap()
    const b = pts.reduce((acc, [x, y]) => [Math.min(acc[0], x), Math.min(acc[1], y), Math.max(acc[2], x), Math.max(acc[3], y)], [999, 999, -999, -999])
    m?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mobile ? { top: 100, bottom: window.innerHeight * 0.5, left: 30, right: 30 } : { top: 100, bottom: 100, left: 620, right: 380 }, maxZoom: 15, duration: 900 })
  }

  // ---------- the slide-over tray: the burger opens it on its menu ('menu'), items open inside it ----------
  // the map shows only favourite spots while that section is open
  const onMenu = (id) => { if (id === 'create') { startCreate(); return } setFavOnly(id === 'favourites'); setPanel(id) }
  const closePanel = () => { setPanel(null); setPanelFull(false); setFavOnly(false); setPerson(null); setEventChat(null) }
  const openChat = (target) => { setDraftPin(null); setEventChat(target); setPanel('messages') }
  // the event a chat belongs to, back on the map: public pins by id, private ones by user_event_id
  const openChatEvent = (info) => {
    const f = featureList.find((x) => (info.kind === 'event' ? x.properties.event_id === info.target_id : x.properties.user_event_id === info.target_id))
    if (!f) return
    if (mobile || panelFull) closePanel()
    openBox(f)
  }
  const toggleTray = () => (panel ? closePanel() : setPanel('menu'))
  const backToMenu = () => { setFavOnly(false); setEventChat(null); setPanel('menu') }

  // ---------- "+ Create event": its own full-height panel on the right ----------
  const startCreate = () => {
    setBoxes([]); setRoute(null); setResults(null); setSheet(null)
    if (mobile || panelFull) closePanel()
    setDraftPin(mapRef.current?.center() || me)
  }
  // Done: the new pin goes straight onto this map (others get public ones from GET /events), then its box opens
  const onCreated = (feature, event) => {
    setFeatures((fc) => ({ type: 'FeatureCollection', features: [...(fc?.features || []).filter((f) => f.properties.event_id !== feature.properties.event_id), feature] }))
    setDraftPin(null)
    if (!values.showInvites) set('showInvites', true)
    say(t('Event created · {audience}', { audience: t(AUDIENCES[event.audience].label) }))
    openBox(feature)
  }

  // ---------- start page <-> map ----------
  const enterMap = ({ q = '', window, category, label, feature, when, where, summary } = {}) => {
    const text = category ? label : summary || q
    setEntryQuery(text)
    if (window) set('timeWindow', window)
    if (when) set('timeWindow', windowFor(when))
    // the map stays still while the pill flies; it searches / moves only once the pill has landed
    flight.current = {
      from: rectOf('.hero-search'), text,
      after: () => {
        if (feature) openBox(feature)
        else if (category) onSearch('events', label || category, { category })
        else if (when || where) showLandingSearch({ q, when, where, summary })
        else if (q.trim()) onSearch('search', q)
        else mapRef.current?.home()
      },
    }
    setFlying(true)
    setView('map')
  }
  // fly the pill for the view change that just rendered (same motion both ways), then let the map move
  useLayoutEffect(() => {
    const f = flight.current
    if (!f) { if (view === 'map') setRevealed(true); return } // e.g. the account pill: no flight
    flight.current = null
    const to = rectOf(view === 'map' ? '.top-left .search' : '.hero-search')
    flySearch(f.from, to, { text: f.text, placeholder: t("What's the plan today?"), reduceMotion: values.reduceMotion }).then(() => {
      setFlying(false)
      if (view === 'map') { setRevealed(true); f.after?.() }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view])
  // start page "what · when · where": filter the loaded pins, list them, frame them on the map
  const showLandingSearch = async ({ q, when, where }) => {
    showSearch(await landingSearch({ q, when, where }, featureList), when ? 'events' : 'search', where)
  }
  // toasts raised from deep components (map box CTAs)
  useEffect(() => {
    const on = (e) => say(e.detail)
    window.addEventListener('syrenka:toast', on)
    return () => window.removeEventListener('syrenka:toast', on)
  }, [say])
  // Escape closes the topmost thing: create panel, then slide-over, then the newest map box / results
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape' || e.target.closest?.('input, textarea, select')) return
      if (draftPin) setDraftPin(null)
      else if (panel) closePanel()
      else if (boxes.length) setBoxes((b) => b.slice(1))
      else if (results) setResults(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  // the account pill (top right, everywhere) opens the profile section of the slide-over
  const openProfile = () => { setDraftPin(null); if (view !== 'map') setView('map'); setFavOnly(false); setPerson(null); setPanel('profile') }
  // a person's pulsing pin on the map ("share my area"): their profile, in the same slide-over
  const openPerson = (id) => { setDraftPin(null); setFavOnly(false); setPerson({ id, at: Date.now() }); setPanel('profile') }
  const goHome = () => {
    flight.current = { from: rectOf('.top-left .search'), text: document.querySelector('.top-left .search input')?.value || '' }
    setFlying(true); setRevealed(false)
    closePanel(); setDraftPin(null); setResults(null); setSheet(null); setView('landing')
  }
  // maximise on Syrenka Selects: back to the start page, then glide down to its Syrenka Selects section
  const showSelectsPage = () => {
    goHome()
    const t0 = Date.now()
    const glide = () => {
      const el = document.getElementById('syrenka-selects')
      if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 650) // once the start page has faded in
      else if (Date.now() - t0 < 3000) requestAnimationFrame(glide)
    }
    requestAnimationFrame(glide)
  }

  const pickResult = (f) => { openBox(f); if (mobile) setSheet('box') }


  const sheetContent = useMemo(() => {
    if (sheet === 'results' && results) return <ResultsList results={results} onPick={pickResult} />
    if (sheet === 'box' && boxes[0]) {
      const b = boxes[0]
      return <MapBox data={b.data} feature={b.feature} journey={b.journey} expanded starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} onChat={openChat} showImage={values.boxImages} />
    }
    return null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheet, results, boxes, fav.ids, values.boxImages, featureList, lang])

  return (
    <div className={`app ${view === 'map' && panel && !mobile ? (panelFull ? 'slide-full' : 'slide-open') : ''} ${view === 'map' && panel && mobile ? 'slide-phone' : ''} ${flying ? 'flying' : ''}`}>
      <MapView ref={mapRef} features={features} busyAreas={busyAreas} route={route} searchArea={results?.area} me={me} favourites={fav.ids} favOnly={favOnly} selectedId={selectedId}
        onPick={(f) => openBox(f, { fly: true })} onMove={setZoom} revealed={revealed} draftPin={draftPin} onDraftPin={setDraftPin}
        city={cityShown} onPickWalk={pickWalk} />
      <PeopleLayer getMap={getMap} show={view === 'map' && values.showPeople !== false} onOpen={openPerson} />

      <AuthLinks />

      <AnimatePresence>{view === 'landing' && <Landing key="landing" features={features ? featureList : null} onEnter={enterMap} getMap={getMap} />}</AnimatePresence>

      <AnimatePresence>{view === 'map' && [

      <div className="top-left" key="top-left">
        <SearchBar onSearch={onSearch} trayOpen={!!panel} unread={myChats.total} onBurger={toggleTray} initialQuery={entryQuery} results={results} onPick={pickResult} onClear={() => { setResults(null); if (sheet === 'results') setSheet(null) }} searching={searching} mobile={mobile} chat={chat} onChatClear={() => setChat([])} features={featureList} />
        <motion.div className="side-controls" initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0, transition: { ...spring, delay: 0.35 } }}>
          {/* the Syrenka: back to the start page (a button, not a toggle) */}
          <motion.button className="btn icon mermaid-btn" onClick={goHome} aria-label={t('Back to the start page')} title={t('Back to the start page')}
            whileTap={{ scale: 0.9 }} transition={spring}>
            <Mermaid />
          </motion.button>
          {/* weather + air quality from the nearest city station (GET /conditions) */}
          <ConditionsChip at={me || WARSAW_CENTER} />
        </motion.div>
      </div>,
      values.showTitle && <h1 className="app-title" key="title">{values.appTitle}</h1>,

      /* under "Log in" / the account pill: close every open map box and the results list */
      // only there while something is open (map boxes, results, the phone's sheet); fades in and out
      !mobile && (boxes.length > 0 || results || sheet) && <motion.button key="close-all" className="close-all" onClick={closeAll}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25, ease: 'easeOut' }}>{t('Close all')}</motion.button>,


      /* desktop map boxes */
      !mobile && (
        <Stage key="boxes" delay={0.4}>
          <div className="boxes scroll-fade" ref={boxesRef}>
            <AnimatePresence>
              {boxes.map((b) => (
                <MapBox key={b.key} layoutId={`box-${b.key}`} data={b.data} feature={b.feature} expanded={b.expanded} journey={b.journey} onClose={() => closeBox(b.key)} onExpand={() => expandBox(b.key)}
                  starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} onChat={openChat} showImage={values.boxImages} />
              ))}
            </AnimatePresence>
          </div>
        </Stage>
      ),

      <Stage key="toolbar" delay={0.45}>
        <BottomToolbar busy={values.busyAreas} onBusy={() => { set('busyAreas', !values.busyAreas); say(t(values.busyAreas ? 'Busy areas off' : 'Busy areas on')) }}
          onZoom={(d) => mapRef.current?.zoomBy(d)} onHome={() => mapRef.current?.home()} me={me} />
      </Stage>,

      // the live API status and the land-use key live in the Data sources panel (SidePanels.jsx)
    ]}</AnimatePresence>

      {/* the slide-over: profiles, messages, favourite spots, sources; switched from its own burger */}
      <AnimatePresence>
        {view === 'map' && panel && (
          <SlideOver key="slideover" section={panel} onSection={onMenu} onBack={backToMenu} onClose={closePanel} full={panelFull}
            onFull={panel === 'selects' && !panelFull ? showSelectsPage : () => setPanelFull((f) => !f)} onHome={goHome} mobile={mobile} unread={myChats.total}>
            {panel === 'selects' && <SelectsRail features={featureList} inSheet single onPick={(f) => { if (mobile || panelFull) closePanel(); openBox(f) }} />}
            {panel === 'profile' && <ProfilePanel person={person} features={featureList} onPick={(f) => { if (mobile || panelFull) closePanel(); openBox(f) }} onFavourites={() => onMenu('favourites')} />}
            {panel === 'messages' && <MessagesPanel chats={myChats} chat={eventChat} onOpenChat={setEventChat} onOpenEvent={openChatEvent} />}
            {panel === 'favourites' && <FavouritesPanel features={featureList} favourites={fav.ids} onPick={(f) => { if (mobile || panelFull) closePanel(); openBox(f) }} />}
            {panel === 'settings' && <SettingsPanel pins={featureList.length} pinCounts={pinCounts} cityCounts={cityCounts} getMap={() => mapRef.current?.getMap()} mobile={mobile} />}
          </SlideOver>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {view === 'map' && draftPin && <CreateEventPanel key="create" pin={draftPin} onClose={() => setDraftPin(null)} onCreated={onCreated} />}
      </AnimatePresence>

      <AccountButton view={view} onProfile={openProfile} />

      {/* the interface editor: on every screen (start page, map, full-screen panel), always on top; its toggle sits left of the account */}

      {DEV_TOOLS && <div className={`top-right on-${view}`}><InterfaceEditor open={editorOpen} onToggle={() => setEditorOpen(!editorOpen)} /></div>}

      {mobile && <BottomSheet open={!!sheet && !!sheetContent} onClose={() => setSheet(null)} initial="half">{sheetContent}</BottomSheet>}

      {DEV_TOOLS && values.debugOverlay && <div className="debug surface">z {zoom.toFixed(2)} · boxes {boxes.length} · fav {fav.ids.size} · {mobile ? 'mobile' : 'desktop'}</div>}

      <AnimatePresence>{toast && <motion.div className="toast surface" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 10, opacity: 0 }}>{toast}</motion.div>}</AnimatePresence>
    </div>
  )
}
