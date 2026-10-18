import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from './config/store'
import { useLang } from './i18n'
import { dataStatus, fetchBusyAreas, fetchCityLayer, fetchFeatures, locateByIp, onAuthChange, runSearch, WARSAW_CENTER } from './data/api'
import { inWindow, onePinPerEvent, windowRange } from './data/features'
import { alongPaths, CITY_LAYERS, walkBoxFeature, walkPaths } from './components/cityLayers'
import { useFavourites } from './hooks/useFavourites'
import { useMapBoxes } from './hooks/useMapBoxes'
import { useSlideOver } from './hooks/useSlideOver'
import { useStartPoint } from './hooks/useStartPoint'
import { useIsMobile } from './hooks/useMedia'
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
import { passesWhenWhere, resolveWhere, smartSearch } from './search/engine'
import { isPast, upcoming } from './data/api'
import { loadAreas } from './search/areas'
import { getMapFilter, passesToggles, setAllTypes, setTypes, useFriendIds, useMapFilter } from './data/mapFilter'
import { typeOf } from './data/types'
import { demoHost } from './demo/host'

/** Map controls arrive part by part after the start page, never all at once. */
const Stage = ({ delay = 0, children }) => (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay, duration: 0.45 } }} exit={{ opacity: 0, transition: { duration: 0.25 } }}>{children}</motion.div>
)

/** Where an element sits on screen right now (null when it isn't rendered). */
const rectOf = (selector) => document.querySelector(selector)?.getBoundingClientRect() ?? null

export default function App() {
  const { values, set, setMany } = useConfig()
  const spring = useSpring()
  const { lang, setLang, t } = useLang()
  const mobile = useIsMobile()
  const mapRef = useRef(null)
  const getMap = useCallback(() => mapRef.current?.getMap(), []) // stable: the start page's network visual keeps its timers across renders
  const fav = useFavourites()

  const [features, setFeatures] = useState(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const myChats = useMyChats()
  useEffect(() => startChatSocket(), []) // live chat messages while logged in (data/chat.js)
  const [view, setView] = useState('landing') // every visit starts on the start page ("Search")
  const [flying, setFlying] = useState(false) // the search pill is in flight between the start page and the map
  const [revealed, setRevealed] = useState(false) // pins and areas shown: only once the pill has landed on the map
  const flight = useRef(null) // { from: DOMRect, text, after } for the next view change
  const [entryQuery, setEntryQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [sheet, setSheet] = useState(null) // mobile: 'results' | 'box' | null
  const [zoom, setZoom] = useState(11.6)
  const [toast, setToast] = useState(null)
  const [busyAreas, setBusyAreas] = useState(null)
  const [me, setMe] = useState(null)
  const start = useStartPoint() // picked in Profile; beats the IP guess
  const firstPosition = useRef(true)
  const [draftPin, setDraftPin] = useState(null) // "+ Create event" is open: where the new event happens
  // the map boxes (and the walking line: the top box's journey) and the slide-over tray
  const { boxes, route, selectedId, listRef: boxesRef, openBox, directions, closeBox, closeTop, closeAll: closeBoxes, expandBox, swapFeatures } = useMapBoxes({ mobile, mapRef, me, setSheet })
  const slide = useSlideOver({ mobile, setSheet, closeCreate: () => setDraftPin(null), onCreate: () => startCreate() })
  const { panel, panelFull, closePanel } = slide
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
  const [chat, setChat] = useState(() => { try { return JSON.parse(localStorage.getItem('warszawa-live.chat.v1') || '[]') } catch { return [] } })
  useEffect(() => { try { localStorage.setItem('warszawa-live.chat.v1', JSON.stringify(chat.map((m) => ({ ...m, results: undefined })))) } catch { /* full / private mode */ } }, [chat])

  // ---------- the pins: loaded once, again on a language switch (titles come translated) and on log in /
  // out (friends-only and invitation pins are per person). Only the newest answer counts, and a failed
  // reload keeps the pins we have instead of emptying the map.
  const featureSeq = useRef(0)
  const loadFeatures = useCallback(() => {
    const n = ++featureSeq.current
    return fetchFeatures().then((fc) => {
      if (n !== featureSeq.current) return
      setFeatures((prev) => (dataStatus.source === 'offline' && prev?.features.length ? prev : fc))
      swapFeatures(fc) // open boxes follow: same event in the new language, a private one you lost closes
    })
  }, [swapFeatures])
  useEffect(() => { loadFeatures(); fetchBusyAreas().then(setBusyAreas) }, [loadFeatures])
  useEffect(() => onAuthChange(loadFeatures), [loadFeatures])
  // one pin per event (GET /events sends one per date), showing its date in the toolbar's time window
  const pins = useMemo(() => onePinPerEvent(features, windowRange(values.timeWindow)), [features, values.timeWindow])
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
    let live = true // a starting point picked meanwhile wins over a late IP answer
    locateByIp().then((loc) => { if (!live) return; setMe(loc.lngLat); say(t(first ? 'Approximate location from your IP · set yours in Profile' : 'Using your approximate IP location')) })
    const poll = setInterval(() => locateByIp().then((loc) => { if (live) setMe(loc.lngLat) }), 5 * 60 * 1000)
    return () => { live = false; clearInterval(poll) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start])
  const featureList = pins?.features || []

  const toastTimer = useRef(null)
  const say = useCallback((t) => { clearTimeout(toastTimer.current); setToast(t); toastTimer.current = setTimeout(() => setToast(null), 1800) }, [])

  // events in the new language after a PL/EN switch (the server sends the translations)
  const firstLang = useRef(true)
  useEffect(() => {
    if (firstLang.current) { firstLang.current = false; return }
    loadFeatures()
  }, [lang]) // eslint-disable-line react-hooks/exhaustive-deps

  // a walking route: its box (journey to the first stop) and the whole line in view
  const pickWalk = (route) => {
    openBox(walkBoxFeature(route), { fly: false })
    fitCoords(route.geometry.coordinates, { desktop: { top: 110, bottom: 110, left: 80, right: 420 }, phoneTop: 120 })
  }
  // frame these [lng, lat] points, clear of the search panel / boxes (desktop) or the sheet (phones)
  const fitCoords = (coords, { desktop = { top: 100, bottom: 100, left: 620, right: 380 }, phoneTop = 100, maxZoom = 15.5 } = {}) => {
    if (!coords.length) return
    const b = coords.reduce((acc, [x, y]) => [Math.min(acc[0], x), Math.min(acc[1], y), Math.max(acc[2], x), Math.max(acc[3], y)], [999, 999, -999, -999])
    mapRef.current?.getMap()?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mobile ? { top: phoneTop, bottom: window.innerHeight * 0.5, left: 30, right: 30 } : desktop, maxZoom, duration: 900 })
  }
  // "Directions" in an event box: the route on our own map, never an outside maps app
  const showDirections = (b) => directions(b.key, b.feature).then((j) => j && fitCoords(j.geometry.coordinates, { maxZoom: 16 }))
  const closeAll = () => { closeBoxes(); setResults(null); if (sheet) setSheet(null); say(t('Closed all map boxes')) }
  const pinCounts = useMemo(() => countPinGroups(featureList, values, fav.ids, slide.favOnly), [featureList, values, fav.ids, slide.favOnly])

  // ---------- the event search's live filter (data/mapFilter.js): which pins the map draws ----------
  const mapFilter = useMapFilter()
  const friendIds = useFriendIds()
  const [filterWhere, setFilterWhere] = useState({ where: null, area: null })
  useEffect(() => { loadAreas().then((areas) => setFilterWhere(resolveWhere(mapFilter.where, areas))) }, [mapFilter.where])
  const searchIds = useMemo(() => {
    if (mapFilter.source !== 'search') return null
    const range = mapFilter.when ? null : windowRange(values.timeWindow) // When replaces the toolbar's time toggle
    return featureList.filter((f) => {
      const p = f.properties
      if (isPast(p) || !passesToggles(p, mapFilter, friendIds)) return false
      if (!inWindow(p, range)) return false
      return !(mapFilter.when || filterWhere.where) || passesWhenWhere(f, mapFilter.when, filterWhere.where)
    }).map((f) => f.properties.event_id)
  }, [featureList, mapFilter, friendIds, filterWhere, values.timeWindow])

  // ---------- search ----------
  const onSearch = async (mode, q, opts) => {
    if (mode === 'events' && opts?.filter) { // the event search: within its toggles, When and Where
      const mf = getMapFilter()
      const anyOn = mf.types.length || mf.users || mf.friends
      const r = await smartSearch(q, upcoming(featureList), {
        mode: 'events', when: mf.when, where: mf.where,
        allowed: anyOn ? (f) => passesToggles(f.properties, mf, friendIds) : () => true,
      })
      // nothing switched on: typed text searched everything, so switch on what it found; nothing typed either: all on
      if (!anyOn) q.trim() ? setTypes(r.results.map((f) => typeOf(f.properties))) : setAllTypes(true)
      showSearch(r, mode, mf.where)
      return
    }
    if (!q.trim() && mode !== 'assistant') { setResults(null); return }
    setSearching(true)
    if (mode === 'assistant') setChat((c) => [...c, { role: 'user', text: q }])
    const r = await runSearch(mode, q, featureList, { ...opts, me })
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
  const fitArea = (area) => fitCoords((area.geometry.type === 'Polygon' ? [area.geometry.coordinates] : area.geometry.coordinates).flatMap((poly) => poly[0]))
  const fitResults = (list) => fitCoords(list.slice(0, 40).map((f) => f.geometry?.coordinates).filter(Boolean), { maxZoom: 15 })

  // ---------- the slide-over tray (hooks/useSlideOver.js) ----------
  // an event picked in the tray opens on the map; the tray steps away where it covers the map
  const pickFromTray = (f) => { slide.closeIfCovering(); openBox(f) }
  // the event a chat belongs to, back on the map: public pins by id, private ones by user_event_id
  const openChatEvent = (info) => {
    const f = featureList.find((x) => (info.kind === 'event' ? x.properties.event_id === info.target_id : x.properties.user_event_id === info.target_id))
    if (f) pickFromTray(f)
  }

  // ---------- "+ Create event": its own full-height panel on the right ----------
  const startCreate = () => {
    closeBoxes(); setResults(null); setSheet(null)
    slide.closeIfCovering()
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
      // a popover (date picker, pin box, language…) that handled Escape itself calls preventDefault
      if (e.key !== 'Escape' || e.defaultPrevented || e.target.closest?.('input, textarea, select')) return
      if (draftPin) setDraftPin(null)
      else if (panel) closePanel()
      else if (boxes.length) closeTop()
      else if (results) setResults(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  // the account pill (top right, everywhere) opens my profile in the slide-over, from the start page too
  const openProfile = () => { if (view !== 'map') setView('map'); slide.openProfile() }
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

  // the presentation demo (double-click Home): the map, the settings it puts back, the create panel it closes
  useEffect(() => { demoHost.current = { getMap, values, setMany, lang, setLang, view, closeCreate: () => setDraftPin(null) } })


  const sheetContent = useMemo(() => {
    if (sheet === 'results' && results) return <ResultsList results={results} onPick={pickResult} />
    if (sheet === 'box' && boxes[0]) {
      const b = boxes[0]
      return <MapBox data={b.data} feature={b.feature} journey={b.journey} expanded onDirections={() => showDirections(b)} starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} onChat={slide.openChat} showImage={values.boxImages} />
    }
    return null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheet, results, boxes, fav.ids, values.boxImages, featureList, lang])

  return (
    <div className={`app ${view === 'map' && panel && !mobile ? (panelFull ? 'slide-full' : 'slide-open') : ''} ${view === 'map' && panel && mobile ? 'slide-phone' : ''} ${flying ? 'flying' : ''}`}>
      <MapView ref={mapRef} features={pins} busyAreas={busyAreas} route={route} searchArea={results?.area || (mapFilter.source === 'search' ? filterWhere.area?.feature : null) || null} searchIds={searchIds} me={me} favourites={fav.ids} favOnly={slide.favOnly} selectedId={selectedId}
        onPick={(f) => openBox(f, { fly: true })} onMove={setZoom} revealed={revealed} draftPin={draftPin} onDraftPin={setDraftPin}
        city={cityShown} onPickWalk={pickWalk} />
      <PeopleLayer getMap={getMap} show={view === 'map' && values.showPeople !== false} onOpen={slide.openPerson} />

      <AuthLinks />

      <AnimatePresence>{view === 'landing' && <Landing key="landing" features={features ? featureList : null} onEnter={enterMap} getMap={getMap} />}</AnimatePresence>

      <AnimatePresence>{view === 'map' && [

      <div className="top-left" key="top-left">
        <SearchBar onSearch={onSearch} matchCount={searchIds?.length || 0} trayOpen={!!panel} unread={myChats.total} onBurger={slide.toggleTray} initialQuery={entryQuery} results={results} onPick={pickResult} onClear={() => { setResults(null); if (sheet === 'results') setSheet(null) }} searching={searching} mobile={mobile} chat={chat} onChatClear={() => setChat([])} features={featureList} />
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
                <MapBox key={b.key} layoutId={`box-${b.key}`} data={b.data} feature={b.feature} expanded={b.expanded} journey={b.journey} onClose={() => closeBox(b.key)} onExpand={() => expandBox(b.key)} onDirections={() => showDirections(b)}
                  starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} onChat={slide.openChat} showImage={values.boxImages} />
              ))}
            </AnimatePresence>
          </div>
        </Stage>
      ),

      <Stage key="toolbar" delay={0.45}>
        <BottomToolbar onZoom={(d) => mapRef.current?.zoomBy(d)} onHome={() => mapRef.current?.home()} me={me} />
      </Stage>,

      // the live API status and the land-use key live in the Data sources panel (SidePanels.jsx)
    ]}</AnimatePresence>

      {/* the slide-over: profiles, messages, favourite spots, sources; switched from its own burger */}
      <AnimatePresence>
        {view === 'map' && panel && (
          <SlideOver key="slideover" section={panel} onSection={slide.onMenu} onBack={slide.backToMenu} onClose={closePanel} full={panelFull}
            onFull={panel === 'selects' && !panelFull ? showSelectsPage : slide.toggleFull} onHome={goHome} mobile={mobile} unread={myChats.total}>
            {panel === 'selects' && <SelectsRail features={featureList} inSheet single onPick={pickFromTray} />}
            {panel === 'profile' && <ProfilePanel person={slide.person} features={featureList} onPick={pickFromTray} onFavourites={() => slide.onMenu('favourites')} />}
            {panel === 'messages' && <MessagesPanel chats={myChats} chat={slide.eventChat} onOpenChat={slide.setEventChat} onOpenEvent={openChatEvent} onOpenUser={slide.openPerson} />}
            {panel === 'favourites' && <FavouritesPanel features={featureList} favourites={fav.ids} onPick={pickFromTray} />}
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

      {/* swiping the event sheet away closes the event too (its route and highlighted pin with it) */}
      {mobile && <BottomSheet open={!!sheet && !!sheetContent} onClose={() => { if (sheet === 'box') closeBoxes(); setSheet(null) }} initial="half">{sheetContent}</BottomSheet>}

      {DEV_TOOLS && values.debugOverlay && <div className="debug surface">z {zoom.toFixed(2)} · boxes {boxes.length} · fav {fav.ids.size} · {mobile ? 'mobile' : 'desktop'}</div>}

      <AnimatePresence>{toast && <motion.div className="toast surface" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 10, opacity: 0 }}>{toast}</motion.div>}</AnimatePresence>
    </div>
  )
}
