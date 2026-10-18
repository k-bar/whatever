import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { dataStatus, routeTo } from '../data/api'
import { useLang } from '../i18n'
import { curate } from '../mapboxes/curate'
import { useScrollFade } from './useScrollFade'

const MAX_OPEN_BOXES = 20 // older boxes stay open and scroll; only past this many does the oldest close

/**
 * The map boxes: the events open on the map, newest on top ([{ key, feature, data, expanded, journey }]),
 * each with its walk from `me` ([lng, lat]). Phones show one at a time, in the event sheet (setSheet).
 * The walking line on the map (route) is always the top box's journey: derived, so a closed box or a
 * late answer for an older box can never leave a line behind.
 */
export function useMapBoxes({ mobile, mapRef, me, setSheet }) {
  const { lang } = useLang()
  const [boxes, setBoxes] = useState([])
  const meRef = useRef(me)
  useEffect(() => { meRef.current = me }, [me])
  // Open boxes stay open: the stack scrolls (soft top / bottom edges, scrollbar only while scrolling)
  const listRef = useScrollFade()

  const route = useMemo(() => {
    const g = boxes[0]?.journey?.geometry
    return g ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: g, properties: {} }] } : null
  }, [boxes])

  const openBox = useCallback((feature, { fly = true } = {}) => {
    const key = String(feature.properties.event_id)
    const data = curate(feature)
    setBoxes((b) => {
      const rest = b.filter((x) => x.key !== key).map((x) => ({ ...x, expanded: false }))
      return [{ key, feature, data, expanded: false }, ...rest].slice(0, mobile ? 1 : MAX_OPEN_BOXES) // phones: one event at a time
    })
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' }) // the newest box goes on top: bring it into view
    if (mobile) setSheet('box')
    if (fly) mapRef.current?.flyTo(feature, 14.5)
    const from = meRef.current
    if (from) {
      setBoxes((b) => b.map((x) => (x.key === key ? { ...x, journey: { pending: true } } : x)))
      routeTo(from, feature.geometry.coordinates).then((j) => {
        setBoxes((b) => b.map((x) => (x.key === key ? { ...x, journey: j } : x)))
      })
    }
  }, [mobile]) // eslint-disable-line react-hooks/exhaustive-deps

  const closeBox = (key) => setBoxes((b) => b.filter((x) => x.key !== key))
  const closeTop = () => setBoxes((b) => b.slice(1))
  const closeAll = () => setBoxes([])
  const expandBox = (key) => setBoxes((b) => b.map((x) => ({ ...x, expanded: x.key === key ? !x.expanded : false })))

  // the pins reloaded (language switch, log in / out): open boxes swap to the same event from the new
  // answer; a private event you can no longer see closes
  const swapFeatures = useCallback((fc) => {
    const byId = new Map(fc.features.map((f) => [String(f.properties.event_id), f]))
    setBoxes((b) => b.flatMap((x) => {
      const f = byId.get(x.key)
      if (f) return [{ ...x, feature: f, data: curate(f) }]
      return x.key.startsWith('ue-') && dataStatus.source !== 'offline' ? [] : [x]
    }))
  }, [])

  // re-curate open boxes so their text follows a language switch
  useEffect(() => {
    setBoxes((b) => b.map((x) => ({ ...x, data: curate(x.feature) })))
  }, [lang])

  return { boxes, route, selectedId: boxes[0]?.key, listRef, openBox, closeBox, closeTop, closeAll, expandBox, swapFeatures }
}
