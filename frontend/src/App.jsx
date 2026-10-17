import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from './config/store'
import { useLang } from './i18n'
import { dataStatus, fetchBusyAreas, fetchFeatures, fetchMapbox, locateByIp, routeTo, runSearch } from './data/api'
import { useFavourites } from './hooks/useFavourites'
import { useStartPoint } from './hooks/useStartPoint'
import { useIsMobile } from './hooks/useMedia'
import { curate } from './mapboxes/curate'
import { BottomSheet } from './components/BottomSheet'
import { BottomToolbar } from './components/BottomToolbar'
import { InterfaceEditor } from './components/InterfaceEditor'
import { LanduseLegend } from './components/LanduseLegend'
import { CloseButton } from './components/CloseButton'
import { Mermaid } from './components/Icons'
import { MapBox } from './components/MapBox'
import { MapView } from './components/MapView'
import { ResultsList, SearchBar } from './components/SearchBar'
import { FavouritesPanel, MessagesPanel, ProfilePanel, SlideOver, SourcesPanel } from './components/SidePanels'
import { Landing } from './components/Landing'
import { SelectsRail } from './components/SelectsRail'
import { CreateEventPanel } from './components/CreateEventPanel'
import { AccountButton } from './components/AccountButton'
import { AUDIENCES } from './data/categories'
import { landingSearch, windowFor } from './landing/search'

/** Map controls arrive part by part after the start page, never all at once. */
const Stage = ({ delay = 0, children }) => (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay, duration: 0.45 } }} exit={{ opacity: 0, transition: { duration: 0.25 } }}>{children}</motion.div>
)

export default function App() {
  const { values, set } = useConfig()
  const spring = useSpring()
  const { lang, t } = useLang()
  const mobile = useIsMobile()
  const mapRef = useRef(null)
  const fav = useFavourites()

  const [features, setFeatures] = useState(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [favOnly, setFavOnly] = useState(false)
  const [panel, setPanel] = useState(null)
  const [panelFull, setPanelFull] = useState(false) // desktop mode 3: the slide-over fills the screen
  const [view, setView] = useState('landing') // every visit starts on the start page ("Search")
  const [entryQuery, setEntryQuery] = useState('')
  const [selectsOpen, setSelectsOpen] = useState(false) // the mermaid button: "Syrenka poleca" in the right bar
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
  const openBox = useCallback(async (feature, { fly = true } = {}) => {
    const key = String(feature.properties.event_id)
    const data = curate(feature)
    setBoxes((b) => {
      const rest = b.filter((x) => x.key !== key).map((x) => ({ ...x, expanded: false }))
      return [{ key, feature, data, expanded: false }, ...rest].slice(0, values.maxBoxes)
    })
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
    const remote = await fetchMapbox(feature) // backend/mapboxes curation wins when available
    if (remote?.blocks) setBoxes((b) => b.map((x) => (x.key === key ? { ...x, remote, data: { ...x.data, ...remote } } : x)))
  }, [mobile, values.maxBoxes])

  // events in the new language after a PL/EN switch (the server sends its translations)
  const firstLang = useRef(true)
  useEffect(() => {
    if (firstLang.current) { firstLang.current = false; return }
    fetchFeatures().then((fc) => {
      setFeatures(fc)
      // open boxes swap to the same event in the new language
      const byId = new Map(fc.features.map((f) => [String(f.properties.event_id), f]))
      setBoxes((b) => b.map((x) => { const f = byId.get(x.key); return f ? { ...x, feature: f, data: { ...curate(f), ...x.remote } } : x }))
    })
  }, [lang])

  // re-curate open boxes so their text follows a language switch
  useEffect(() => {
    setBoxes((b) => b.map((x) => ({ ...x, data: { ...curate(x.feature), ...x.remote } })))
  }, [lang])

  const closeBox = (key) => setBoxes((b) => { const n = b.filter((x) => x.key !== key); if (!n.length) setRoute(null); return n })
  const closeAll = () => { setBoxes([]); setResults(null); setRoute(null); if (sheet) setSheet(null); say(t('Closed all map boxes')) }
  const expandBox = (key) => setBoxes((b) => b.map((x) => ({ ...x, expanded: x.key === key ? !x.expanded : false })))
  const selectedId = boxes[0]?.key

  // ---------- search ----------
  const onSearch = async (mode, q, opts) => {
    if (!q.trim() && mode !== 'assistant') { setResults(null); return }
    setSearching(true)
    if (mode === 'assistant') setChat((c) => [...c, { role: 'user', text: q }])
    const r = await runSearch(mode, q, featureList, opts)
    setSearching(false)
    if (mode === 'assistant') { setChat((c) => [...c, { role: 'assistant', text: r.answer, results: r.results }]) } else { setResults({ mode, q, ...r }); if (mobile) setSheet('results') }
    if (r.results?.length && r.results.length <= 40) fitResults(r.results)
  }
  const fitResults = (list) => {
    const pts = list.slice(0, 40).map((f) => f.geometry?.coordinates).filter(Boolean)
    if (!pts.length) return
    const m = mapRef.current?.getMap()
    const b = pts.reduce((acc, [x, y]) => [Math.min(acc[0], x), Math.min(acc[1], y), Math.max(acc[2], x), Math.max(acc[3], y)], [999, 999, -999, -999])
    m?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mobile ? { top: 100, bottom: window.innerHeight * 0.5, left: 30, right: 30 } : { top: 100, bottom: 100, left: 620, right: 380 }, maxZoom: 15, duration: 900 })
  }

  // the map shows only favourite spots while that section of the slide-over is open
  const onMenu = (id) => { if (id === 'create') { startCreate(); return } setFavOnly(id === 'favourites'); setPanel(id) }
  const closePanel = () => { setPanel(null); setPanelFull(false); setFavOnly(false) }

  // ---------- "+ Create event": its own full-height panel on the right ----------
  const startCreate = () => {
    setBoxes([]); setRoute(null); setResults(null); setSheet(null); setSelectsOpen(false)
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
    setEntryQuery(category ? label : summary || q)
    setView('map')
    if (window) set('timeWindow', window)
    if (when) set('timeWindow', windowFor(when))
    // act once the search pill has landed in its corner, so the scene improves instead of jumping
    setTimeout(() => {
      if (feature) openBox(feature)
      else if (category) onSearch('events', label || category, { category })
      else if (when || where) showLandingSearch({ q, when, where, summary })
      else if (q.trim()) onSearch('search', q)
      else mapRef.current?.home()
    }, 520)
  }
  // start page "what · when · where": filter the loaded pins, list them, frame them on the map
  const showLandingSearch = ({ q, when, where, summary }) => {
    const list = landingSearch({ q, when, where }, featureList)
    setResults({ mode: when ? 'events' : 'search', q: summary, results: list })
    if (mobile) setSheet('results')
    if (list.length) fitResults(list)
    else if (where?.lngLat) mapRef.current?.getMap()?.flyTo({ center: where.lngLat, zoom: 15, duration: 1100 })
  }
  // Escape closes the topmost thing: create panel, then slide-over, then the newest map box / results
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape' || e.target.closest?.('input, textarea, select')) return
      if (draftPin) setDraftPin(null)
      else if (panel) closePanel()
      else if (selectsOpen) setSelectsOpen(false)
      else if (boxes.length) setBoxes((b) => b.slice(1))
      else if (results) setResults(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  // the account pill (top right, everywhere) opens the profile section of the slide-over
  const openProfile = () => { setDraftPin(null); if (view !== 'map') setView('map'); setFavOnly(false); setPanel('profile') }
  const goHome = () => { closePanel(); setDraftPin(null); setResults(null); setSheet(null); setView('landing') }

  const pickResult = (f) => { openBox(f); if (mobile) setSheet('box') }

  const toggleSelects = () => {
    if (mobile) { setSelectsOpen(false); setSheet(sheet === 'selects' ? null : 'selects'); return }
    setSelectsOpen((v) => !v)
  }

  const sheetContent = useMemo(() => {
    if (sheet === 'results' && results) return <ResultsList results={results} onPick={pickResult} />
    if (sheet === 'selects') return <SelectsRail inSheet features={featureList} onPick={(f) => { openBox(f); setSheet('box') }} />
    if (sheet === 'box' && boxes[0]) {
      const b = boxes[0]
      return <MapBox data={b.data} feature={b.feature} journey={b.journey} expanded starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} showImage={values.boxImages} />
    }
    return null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheet, results, boxes, fav.ids, values.boxImages, featureList, lang])

  return (
    <div className={`app ${view === 'map' && panel && !mobile ? (panelFull ? 'slide-full' : 'slide-open') : ''}`}>
      <MapView ref={mapRef} features={features} busyAreas={busyAreas} route={route} me={me} favourites={fav.ids} favOnly={favOnly} selectedId={selectedId}
        onPick={(f) => openBox(f, { fly: true })} onMove={setZoom} revealed={view === 'map'} draftPin={draftPin} onDraftPin={setDraftPin} />

      <AnimatePresence>{view === 'landing' && <Landing key="landing" features={features ? featureList : null} onEnter={enterMap} />}</AnimatePresence>

      <AnimatePresence>{view === 'map' && [

      <div className="top-left" key="top-left">
        <SearchBar onSearch={onSearch} onMenu={onMenu} onHome={goHome} initialQuery={entryQuery} results={results} onPick={pickResult} onClear={() => { setResults(null); if (sheet === 'results') setSheet(null) }} searching={searching} mobile={mobile} chat={chat} onChatClear={() => setChat([])} />
        <motion.div className="side-controls" initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0, transition: { ...spring, delay: 0.35 } }}>
          <motion.button className={`btn icon mermaid-btn ${selectsOpen ? 'active' : ''}`} onClick={toggleSelects} aria-label={t('Syrenka Selects')} title={t('Syrenka Selects')}
            whileTap={{ scale: 0.85 }} animate={selectsOpen ? { rotate: [0, -8, 8, 0] } : {}} transition={spring}>
            <Mermaid />
          </motion.button>
          <CloseButton onClick={closeAll} label={t('Close all map boxes')} animate={{ opacity: boxes.length || results ? 1 : 0.55 }} />
        </motion.div>
      </div>,
      values.showTitle && <h1 className="app-title" key="title">{values.appTitle}</h1>,

      /* top-right: editor toggle lives inside InterfaceEditor */
      <Stage key="top-right" delay={0.55}><div className="top-right"><InterfaceEditor open={editorOpen} onToggle={() => setEditorOpen(!editorOpen)} /></div></Stage>,

      /* desktop map boxes */
      !mobile && (
        <Stage key="boxes" delay={0.4}>
          <div className="boxes">
            <AnimatePresence>
              {selectsOpen && <SelectsRail key="selects" features={featureList} onClose={() => setSelectsOpen(false)} onPick={(f) => { setSelectsOpen(false); openBox(f) }} />}
              {boxes.map((b) => (
                <MapBox key={b.key} layoutId={`box-${b.key}`} data={b.data} feature={b.feature} expanded={b.expanded} journey={b.journey} onClose={() => closeBox(b.key)} onExpand={() => expandBox(b.key)}
                  starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} showImage={values.boxImages} />
              ))}
            </AnimatePresence>
          </div>
        </Stage>
      ),

      <Stage key="toolbar" delay={0.45}>
        <BottomToolbar busy={values.busyAreas} onBusy={() => { set('busyAreas', !values.busyAreas); say(t(values.busyAreas ? 'Busy areas off' : 'Busy areas on')) }}
          onZoom={(d) => mapRef.current?.zoomBy(d)} onHome={() => mapRef.current?.home()} layersOn={values.showPlaces} onLayers={() => set('showPlaces', !values.showPlaces)} />
      </Stage>,

      <Stage key="legend" delay={0.6}><LanduseLegend getMap={() => mapRef.current?.getMap()} mobile={mobile} /></Stage>,
      values.apiBadge && <Stage key="badge" delay={0.65}><div className={`data-badge surface ${dataStatus.source}`}><i />{t(dataStatus.source === 'api' ? 'live API' : dataStatus.source === 'offline' ? 'API offline' : 'loading…')} · {featureList.length} {t('pins')}</div></Stage>,
    ]}</AnimatePresence>

      {/* the slide-over: profiles, messages, favourite spots, sources; switched from its own burger */}
      <AnimatePresence>
        {view === 'map' && panel && (
          <SlideOver key="slideover" section={panel} onSection={onMenu} onClose={closePanel} full={panelFull} onFull={() => setPanelFull((f) => !f)} onHome={goHome} mobile={mobile}>
            {panel === 'profile' && <ProfilePanel />}
            {panel === 'messages' && <MessagesPanel />}
            {panel === 'favourites' && <FavouritesPanel features={featureList} favourites={fav.ids} onPick={(f) => { if (mobile || panelFull) closePanel(); openBox(f) }} />}
            {panel === 'sources' && <SourcesPanel />}
          </SlideOver>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {view === 'map' && draftPin && <CreateEventPanel key="create" pin={draftPin} onClose={() => setDraftPin(null)} onCreated={onCreated} />}
      </AnimatePresence>

      <AccountButton view={view} onProfile={openProfile} />

      {mobile && <BottomSheet open={!!sheet && !!sheetContent} onClose={() => setSheet(null)} initial="half">{sheetContent}</BottomSheet>}

      {values.debugOverlay && <div className="debug surface">z {zoom.toFixed(2)} · boxes {boxes.length} · fav {fav.ids.size} · {mobile ? 'mobile' : 'desktop'}</div>}

      <AnimatePresence>{toast && <motion.div className="toast surface" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 10, opacity: 0 }}>{toast}</motion.div>}</AnimatePresence>
    </div>
  )
}
