import { useEffect, useRef, useState } from 'react'
import { useLang } from '../i18n'
import { locateByDevice, searchAddress } from '../data/api'
import { setStartPoint, useStartPoint } from '../hooks/useStartPoint'

/**
 * "Set my location to": the user's starting point for routes and travel times.
 * IP geolocation is only ~1-5 km accurate, so the user can search an address or postcode,
 * or use the device's GPS. The point is saved in the browser and shared via useStartPoint.
 */
export function StartPointPicker() {
  const { t } = useLang()
  const start = useStartPoint()
  const onSet = setStartPoint
  const [q, setQ] = useState('')
  const [hits, setHits] = useState([])
  const [state, setState] = useState('idle') // idle | searching | locating | error
  const timer = useRef(null)
  const ctl = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    clearTimeout(timer.current)
    ctl.current?.abort()
    if (q.trim().length < 2) { setHits([]); setState('idle'); return }
    timer.current = setTimeout(async () => {
      ctl.current = new AbortController()
      setState('searching')
      try { setHits(await searchAddress(q.trim(), { signal: ctl.current.signal })); setState('idle') } catch (e) { if (e.name !== 'AbortError') setState('error') }
    }, 300)
    return () => clearTimeout(timer.current)
  }, [q])

  const pick = (p) => { onSet({ lngLat: p.lngLat, label: p.label, sub: p.sub }); setQ(''); setHits([]) }
  const useDevice = async () => {
    setState('locating')
    // no position (permission denied, no GPS fix): say so and hand the choice back to the user
    try { pick(await locateByDevice()); setState('idle') } catch { setState('error'); inputRef.current?.focus() }
  }

  return (
    <div className="start-picker">
      <div className="sp-current">
        <PinGlyph />
        <span>
          <div className="t">{start ? start.label : t('Approximate (from your IP)')}</div>
          <div className="s">{start ? (start.sub || t('Your starting point')) : t('Pick an address for accurate travel times')}</div>
        </span>
        {start && <button className="btn small" onClick={() => onSet(null)}>{t('Use IP')}</button>}
      </div>

      <label className="start-input">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Address or postcode, e.g. 02-591')}
          onKeyDown={(e) => { if (e.key === 'Enter' && hits[0]) pick(hits[0]) }} aria-label={t('Search an address or postcode')} />
        {state === 'searching' && <span className="spin" />}
      </label>

      {hits.length > 0 && (
        <div className="start-hits">
          {hits.map((h, i) => (
            <button key={i} className="start-hit" onClick={() => pick(h)}>
              <span className="t">{h.label}</span>{h.sub && <span className="s">{h.sub}</span>}
            </button>
          ))}
        </div>
      )}
      {q.trim().length >= 2 && state === 'idle' && !hits.length && <div className="start-note warn">{t("I can't find it. Try another address or postcode.")}</div>}
      {state === 'error' && <div className="start-note warn">{t("I can't find it. Please choose your starting point: type your address or postcode above.")}</div>}

      <button className="btn small start-gps" onClick={useDevice} disabled={state === 'locating'}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>
        {state === 'locating' ? t('Locating…') : t('Use my device location')}
      </button>
    </div>
  )
}

/** The same pin as the "me" marker on the map. */
export function PinGlyph({ size = 26 }) {
  return (
    <svg className="pin-glyph" width={size} height={size * 4 / 3} viewBox="0 0 30 40" aria-hidden="true">
      <path d="M15 38.5C15 38.5 3 24.6 3 15a12 12 0 0 1 24 0c0 9.6-12 23.5-12 23.5Z" fill="#4fb3ff" stroke="#fff" strokeWidth="2.6" strokeLinejoin="round" />
      <circle cx="15" cy="15" r="5" fill="#fff" />
    </svg>
  )
}
