import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { assetUrl, onAuthChange } from '../data/api'
import { refreshPeople, usePeople } from '../data/people'
import { useLang } from '../i18n'

/**
 * People who "share their area": a round photo on the map with rings radiating out of it ("I'm around,
 * come and hang out"). Tap one to open their profile in the slide-over. HTML markers so CSS can animate
 * them; a small dot marks the ones hosting an open invitation, a green rim your friends.
 * Shown while the toolbar's People switch is on (config `showPeople`), refreshed every minute.
 */
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

function element(p, t) {
  const el = document.createElement('div')
  el.className = `person-marker${p.is_friend ? ' friend' : ''}${p.hosting ? ' hosting' : ''}`
  el.style.setProperty('--pulse-delay', `${-((p.id * 0.37) % 2.4).toFixed(2)}s`) // not all in step
  const photo = p.photos?.[0]
  const first = p.display_name.split(' ')[0]
  el.innerHTML = '<span class="pr-ring"></span><span class="pr-ring r2"></span><span class="pr-ring r3"></span>'
    + `<button type="button" class="pr-av" aria-label="${esc(t('Open the profile of {name}', { name: p.display_name }))}" title="${esc(p.display_name)} · @${esc(p.username)}">`
    + (photo ? `<img src="${esc(assetUrl(photo))}" alt="" draggable="false">` : `<span>${esc(first[0] || '?')}</span>`)
    + '</button>'
    + `<span class="pr-name">${esc(first)}</span>`
  return el
}

export function PeopleLayer({ getMap, show, onOpen }) {
  const { t } = useLang()
  const { people } = usePeople()
  const markers = useRef(new Map()) // user id -> { marker, key }
  const openRef = useRef(onOpen)
  openRef.current = onOpen
  const [tick, setTick] = useState(0) // retry until the map exists

  useEffect(() => {
    if (!show) return
    refreshPeople()
    const id = setInterval(refreshPeople, 60_000)
    const off = onAuthChange(refreshPeople)
    return () => { clearInterval(id); off() }
  }, [show])

  useEffect(() => {
    const m = getMap()
    if (!m) { const id = setTimeout(() => setTick((n) => n + 1), 300); return () => clearTimeout(id) }
    const want = new Map(show ? people.filter((p) => !p.is_self).map((p) => [p.id, p]) : [])
    for (const [id, { marker }] of markers.current) {
      if (!want.has(id)) { marker.remove(); markers.current.delete(id) }
    }
    for (const p of want.values()) {
      const key = `${p.display_name}|${p.photos?.[0]}|${p.is_friend}|${!!p.hosting}|${t('Open the profile of {name}', { name: '' })}`
      const have = markers.current.get(p.id)
      if (have && have.key === key) { have.marker.setLngLat([p.lng, p.lat]); continue }
      have?.marker.remove()
      const el = element(p, t)
      el.querySelector('.pr-av').addEventListener('click', (e) => { e.stopPropagation(); openRef.current?.(p.id) })
      markers.current.set(p.id, { key, marker: new maplibregl.Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(m) })
    }
  }, [people, show, getMap, t, tick])

  useEffect(() => () => { for (const { marker } of markers.current.values()) marker.remove(); markers.current.clear() }, [])
  return null
}
