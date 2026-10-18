import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchConditions, haversineKm } from '../data/api'
import { useSpring } from '../config/store'
import { locale, useLang } from '../i18n'
import { usePopover } from '../hooks/usePopover'

const REFRESH_MS = 10 * 60 * 1000 // the backend refreshes its stations every 10 minutes
const STALE_MS = 3 * 60 * 60 * 1000 // ignore stations that haven't reported for 3 hours

// the city's air quality index (Polish names from the API) -> English key + colour
const AIR = {
  'bardzo dobry': ['Very good', '#0fa37f'],
  dobry: ['Good', '#5bb14a'],
  umiarkowany: ['Moderate', '#f2a900'],
  dostateczny: ['Sufficient', '#f97316'],
  'zły': ['Bad', '#e7392b'],
  'bardzo zły': ['Very bad', '#9b1c1c'],
}

/** The closest station that reported recently and has the value we need. */
function nearest(fc, at, ok) {
  let best = null, bestKm = Infinity
  for (const f of fc?.features || []) {
    const p = f.properties
    if (!ok(p) || (p.measured_at && Date.now() - new Date(p.measured_at) > STALE_MS)) continue
    const km = haversineKm(at, f.geometry.coordinates)
    if (km < bestKm) { best = p; bestKm = km }
  }
  return best
}

/**
 * Weather and air quality where you are (the nearest city station and sensor, GET /conditions):
 * a small pill on the map — temperature + air quality; tap for wind, rain, humidity and the city's advice.
 */
export function ConditionsChip({ at }) {
  const { t } = useLang()
  const spring = useSpring()
  const [data, setData] = useState(null)
  const { open, setOpen, ref } = usePopover() // closes on a tap outside and on Escape

  useEffect(() => {
    let alive = true
    const load = () => fetchConditions().then((d) => { if (alive && d) setData(d) })
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])


  if (!data || !at) return null
  const w = nearest(data.weather, at, (p) => p.temp_air != null)
  const a = nearest(data.air, at, (p) => AIR[String(p.index || '').toLowerCase()])
  if (!w && !a) return null
  const [airLabel, airColor] = a ? AIR[a.index.toLowerCase()] : []
  const num = (n, d = 0) => Number(n).toLocaleString(locale(), { maximumFractionDigits: d })

  return (
    <div className="cond" ref={ref}>
      <button className={`cond-chip ${open ? 'open' : ''}`} onClick={() => setOpen(!open)} aria-expanded={open} style={{ '--cond-air': airColor }}
        title={t('Weather and air quality near you')}>
        {w && <span className="cond-temp">{num(w.temp_air)}°</span>}
        {a && <span className="cond-air"><i style={{ background: airColor }} />{t('Air')}: {t(airLabel)}</span>}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="cond-pop surface" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={spring}>
            {w && (
              <div className="cond-sec">
                <div className="cond-h">{t('Weather')} <span>· {w.name}</span></div>
                <div className="cond-row"><span>{t('Temperature')}</span><b>{num(w.temp_air, 1)}°C</b></div>
                {w.wind_speed != null && <div className="cond-row"><span>{t('Wind')}</span><b>{num(w.wind_speed, 1)} m/s</b></div>}
                {w.precipitation != null && <div className="cond-row"><span>{t('Rain')}</span><b>{num(w.precipitation, 1)} mm</b></div>}
                {w.humidity != null && <div className="cond-row"><span>{t('Humidity')}</span><b>{num(w.humidity)}%</b></div>}
              </div>
            )}
            {a && (
              <div className="cond-sec">
                <div className="cond-h">{t('Air quality')} <span>· {a.street || a.station || a.name}</span></div>
                <div className="cond-row"><span><i className="cond-dot" style={{ background: airColor }} />{t(airLabel)}</span>
                  {a.params?.['PM2.5']?.value != null && <b>PM2.5 {num(a.params['PM2.5'].value)} µg/m³</b>}</div>
                {/* the city's own advice comes in Polish */}
                {a.recommendation && <p className="cond-note">{a.recommendation}</p>}
              </div>
            )}
            <div className="cond-src">{t('Warsaw Open Data · updated every 10 min')}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
