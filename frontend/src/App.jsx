import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from './config/store'
import { dataStatus, fetchBusyAreas, fetchFeatures, fetchMapbox, locateByIp, routeTo, runSearch } from './data/api'
import { useFavourites } from './hooks/useFavourites'
import { useIsMobile } from './hooks/useMedia'
import { curate } from './mapboxes/curate'
import { BottomSheet } from './components/BottomSheet'
import { BottomToolbar } from './components/BottomToolbar'
import { InterfaceEditor } from './components/InterfaceEditor'
import { CloseButton } from './components/CloseButton'
import { Mermaid } from './components/Icons'
import { MapBox } from './components/MapBox'
import { MapView } from './components/MapView'
import { ResultsList, SearchBar } from './components/SearchBar'
import { FavouritesPanel, MessagesPanel, ProfilePanel, SourcesPanel } from './components/SidePanels'

export default function App() {
  const { values, set } = useConfig()
  const spring = useSpring()
  const mobile = useIsMobile()
  const mapRef = useRef(null)
  const fav = useFavourites()

  const [features, setFeatures] = useState(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [favOnly, setFavOnly] = useState(false)
  const [panel, setPanel] = useState(null)
  const [boxes, setBoxes] = useState([]) // [{ key, feature, data, expanded }]
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [sheet, setSheet] = useState(null) // mobile: 'results' | 'box' | null
  const [zoom, setZoom] = useState(11.6)
  const [toast, setToast] = useState(null)
  const [busyAreas, setBusyAreas] = useState(null)
  const [me, setMe] = useState(null)
  const [route, setRoute] = useState(null)
  const meRef = useRef(null)
  useEffect(() => { meRef.current = me }, [me])
  const [chat, setChat] = useState(() => { try { return JSON.parse(localStorage.getItem('warszawa-live.chat.v1') || '[]') } catch { return [] } })
  useEffect(() => { localStorage.setItem('warszawa-live.chat.v1', JSON.stringify(chat.map((m) => ({ ...m, results: undefined })))) }, [chat])

  useEffect(() => {
    fetchFeatures().then(setFeatures); fetchBusyAreas().then(setBusyAreas)
    // "You are here": IP position on load, re-polled every 5 minutes (the IP changes when the user moves networks)
    locateByIp().then((loc) => { setMe(loc.lngLat); say(`You are here · ${loc.label}`) })
    const poll = setInterval(() => locateByIp().then((loc) => setMe(loc.lngLat)), 5 * 60 * 1000)
    return () => clearInterval(poll)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
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
    if (remote?.blocks) setBoxes((b) => b.map((x) => (x.key === key ? { ...x, data: { ...x.data, ...remote } } : x)))
  }, [mobile, values.maxBoxes])

  const closeBox = (key) => setBoxes((b) => { const n = b.filter((x) => x.key !== key); if (!n.length) setRoute(null); return n })
  const closeAll = () => { setBoxes([]); setResults(null); setRoute(null); if (sheet) setSheet(null); say('Closed all map boxes') }
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
    if (r.results?.length && r.results.length <= 40) {
      const m = mapRef.current?.getMap()
      const b = r.results.reduce((acc, f) => { const [x, y] = f.geometry.coordinates; return [Math.min(acc[0], x), Math.min(acc[1], y), Math.max(acc[2], x), Math.max(acc[3], y)] }, [999, 999, -999, -999])
      m?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mobile ? { top: 100, bottom: window.innerHeight * 0.5, left: 30, right: 30 } : { top: 100, bottom: 100, left: 620, right: 380 }, maxZoom: 15, duration: 900 })
    }
  }

  const onMenu = (id) => {
    if (id === 'favourites') { setFavOnly(true); setPanel('favourites'); return }
    setPanel(id)
  }

  const pickResult = (f) => { openBox(f); if (mobile) setSheet('box') }

  const toggleFavOnly = () => { setFavOnly((v) => !v); say(favOnly ? 'Showing everything' : 'Showing your favourite spots') }

  const sheetContent = useMemo(() => {
    if (sheet === 'results' && results) return <ResultsList results={results} onPick={pickResult} />
    if (sheet === 'box' && boxes[0]) {
      const b = boxes[0]
      return <MapBox data={b.data} feature={b.feature} journey={b.journey} expanded starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} showImage={values.boxImages} />
    }
    return null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheet, results, boxes, fav.ids, values.boxImages])

  return (
    <div className="app">
      <MapView ref={mapRef} features={features} busyAreas={busyAreas} route={route} me={me} favourites={fav.ids} favOnly={favOnly} selectedId={selectedId}
        onPick={(f) => openBox(f, { fly: true })} onMove={setZoom} />

      {/* top-left: search pill + mermaid (as tall as the search bar) + (x) */}
      <div className="top-left">
        <SearchBar onSearch={onSearch} onMenu={onMenu} results={results} onPick={pickResult} onClear={() => { setResults(null); if (sheet === 'results') setSheet(null) }} searching={searching} mobile={mobile} chat={chat} onChatClear={() => setChat([])} />
        <div className="side-controls">
          <motion.button className={`btn icon mermaid-btn ${favOnly ? 'active' : ''}`} onClick={toggleFavOnly} aria-label="My favourite spots" title="My favourite spots"
            whileTap={{ scale: 0.85 }} animate={favOnly ? { rotate: [0, -8, 8, 0] } : {}} transition={spring}>
            <Mermaid />
          </motion.button>
          <CloseButton onClick={closeAll} label="Close all map boxes" animate={{ opacity: boxes.length || results ? 1 : 0.55 }} />
        </div>
      </div>
      {values.showTitle && <h1 className="app-title">{values.appTitle}</h1>}

      {/* top-right: editor toggle lives inside InterfaceEditor */}
      <div className="top-right"><InterfaceEditor open={editorOpen} onToggle={() => setEditorOpen(!editorOpen)} /></div>

      {/* desktop map boxes */}
      {!mobile && (
        <div className="boxes">
          <AnimatePresence>
            {boxes.map((b) => (
              <MapBox key={b.key} layoutId={`box-${b.key}`} data={b.data} feature={b.feature} expanded={b.expanded} journey={b.journey} onClose={() => closeBox(b.key)} onExpand={() => expandBox(b.key)}
                starred={fav.has(b.key)} onStar={() => fav.toggle(b.key)} showImage={values.boxImages} />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* side panels from the burger menu */}
      <AnimatePresence>
        {panel === 'profile' && <ProfilePanel key="p" onClose={() => setPanel(null)} />}
        {panel === 'messages' && <MessagesPanel key="m" onClose={() => setPanel(null)} />}
        {panel === 'favourites' && <FavouritesPanel key="f" onClose={() => setPanel(null)} features={featureList} favourites={fav.ids} onPick={(f) => { setPanel(null); openBox(f) }} />}
        {panel === 'sources' && <SourcesPanel key="s" onClose={() => setPanel(null)} />}
      </AnimatePresence>

      <BottomToolbar busy={values.busyAreas} onBusy={() => { set('busyAreas', !values.busyAreas); say(values.busyAreas ? 'Busy areas off' : 'Busy areas on') }}
        onZoom={(d) => mapRef.current?.zoomBy(d)} onHome={() => mapRef.current?.home()} layersOn={values.showPlaces} onLayers={() => set('showPlaces', !values.showPlaces)} />

      {mobile && <BottomSheet open={!!sheet && !!sheetContent} onClose={() => setSheet(null)} initial="half">{sheetContent}</BottomSheet>}

      {values.apiBadge && <div className={`data-badge surface ${dataStatus.source}`}><i />{dataStatus.source === 'api' ? 'live API' : dataStatus.source === 'mock' ? 'mock data · API offline' : 'loading…'} · {featureList.length} pins</div>}
      {values.debugOverlay && <div className="debug surface">z {zoom.toFixed(2)} · boxes {boxes.length} · fav {fav.ids.size} · {mobile ? 'mobile' : 'desktop'}</div>}

      <AnimatePresence>{toast && <motion.div className="toast surface" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 10, opacity: 0 }}>{toast}</motion.div>}</AnimatePresence>
    </div>
  )
}
