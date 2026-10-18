import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { CATEGORIES, categoryColor, categoryLabel } from '../data/categories'
import { typeColor, typeLabel, typeOf } from '../data/types'
import { useLang } from '../i18n'
import { pickSelects, secureImage } from '../landing/selects'
import { fmtWhen } from '../mapboxes/curate'
import { Brand } from './Brand'
import { LandingSearch } from './LandingSearch'
import { FlagPL, FlagUK } from './LangSwitch'
import { Calendar as CalendarIcon, Chevron, Flame, Layers, MapIcon, Mermaid, Music, Sparkle, Ticket, Users } from './Icons'
import { LandingNetwork } from './LandingNetwork'
import { useIsMobile } from '../hooks/useMedia'
import { useSocial } from '../data/social'

// Quick tiles under the search. Colours come from our category palette; the "together" tiles carry a
// people badge to say this is user-made content (public invitations), not just listings.
const TILES = [
  { label: 'Concerts', category: 'music', Icon: Music },
  { label: 'Theatre & film', category: 'theatre', Icon: Ticket },
  { label: 'Picnic together', category: 'meetups', people: true, Icon: Sparkle },
  { label: 'Concert together', category: 'music', people: true, Icon: Music },
  { label: 'Sightseeing tour', category: 'culture', people: true, Icon: MapIcon },
  { label: 'More', more: true, Icon: Chevron },
]

/** One of the six big tiles: pops in once when the page opens; hover / press are transform-only. */
function Tile({ tile, onClick, delay = 0, open }) {
  const { t } = useLang()
  const c = tile.more ? 'var(--fg)' : categoryColor(tile.category)
  const I = tile.Icon
  return (
    <motion.button className={`hero-tile ${tile.people ? 'people' : ''} ${tile.more ? 'more' : ''}`} style={{ '--c': c }} onClick={onClick}
      aria-expanded={tile.more ? open : undefined}
      initial={{ opacity: 0, y: 14, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 420, damping: 28, delay }} whileHover={{ y: -3, scale: 1.03 }} whileTap={{ scale: 0.96 }}>
      <span className="tile-ic">{I && <I size={20} />}</span>
      {tile.people && <span className="tile-people" title={t('Made by people like you')}><Users size={14} /></span>}
      <span className="tile-label">{t(tile.label)}</span>
      {tile.more && <span className={`tile-chev ${open ? 'open' : ''}`}><Chevron size={16} /></span>}
    </motion.button>
  )
}

/**
 * "More": every category as small tiles under the big ones. Always in the page; opening it is pure CSS (the row
 * grows with a grid-template-rows transition, the tiles fade in with a short stagger), so nothing is measured or
 * re-laid-out frame by frame. Closed, it takes no space and can't be tabbed into.
 */
function MoreTiles({ open, onPick }) {
  const allCats = Object.keys(CATEGORIES).filter((slug) => slug !== 'other')
  return (
    <div className={`more-tiles ${open ? 'open' : ''}`} aria-hidden={!open} {...(!open && { inert: '' })}>
      <div className="more-tiles-inner">
        <div className="hero-tiles all">
          {allCats.map((slug, i) => (
            <button key={slug} className="hero-tile small" style={{ '--c': categoryColor(slug), '--i': i }} onClick={() => onPick(slug)}>
              <span className="tile-ic" />
              <span className="tile-label">{categoryLabel(slug)}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/**
 * The start page ("Search"): headline + big search over the live map (washed out), quick chips, and
 * "Syrenka poleca" below. Nothing here reloads the map: entering just fades the wash away while the
 * search pill (shared layoutId "search-pill") flies to its top-left spot on the map.
 */
export function Landing({ features, onEnter, getMap }) {
  const { t, lang, setLang } = useLang()
  const mobile = useIsMobile()
  const spring = useSpring()
  const scroller = useRef(null)
  const [more, setMore] = useState(false)
  const [broken, setBroken] = useState(() => new Set()) // posters that failed to load drop out of Syrenka Selects
  const social = useSocial()
  const selects = useMemo(() => pickSelects(features, { social }).filter(({ feature: f }) => !broken.has(f.properties.event_id)), [features, broken, social])
  const loading = !features

  // Keep the search pill in the middle of the screen: the space above the headline is whatever puts the
  // pill's centre at half the viewport. Syrenka Selects follows the tiles directly, so its first cards
  // peek in at the bottom. Re-measured when the headline / pill change size or the window resizes.
  const center = useRef(null)
  const grid = useRef(null)
  const showSelects = () => {
    const sc = scroller.current, g = grid.current
    if (!sc || !g) return
    sc.scrollTo({ top: sc.scrollTop + g.getBoundingClientRect().top - sc.getBoundingClientRect().top - 16, behavior: 'smooth' })
  }
  useLayoutEffect(() => {
    const el = center.current
    const pill = el?.querySelector('.hero-search')
    if (!pill) return
    const fit = () => {
      const pad = parseFloat(getComputedStyle(el).paddingTop) || 0
      const pillMid = el.offsetTop + pill.offsetTop + pill.offsetHeight / 2 // layout position, ignores entrance transforms
      const view = scroller.current?.clientHeight || window.innerHeight
      el.style.paddingTop = `${Math.max(12, pad + view / 2 - pillMid)}px`
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(pill); ro.observe(el.querySelector('h1'))
    window.addEventListener('resize', fit)
    document.fonts?.ready.then(fit)
    return () => { ro.disconnect(); window.removeEventListener('resize', fit) }
  }, [])

  return (
    <motion.div className="landing" ref={scroller} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.65, ease: 'easeInOut' } }}>
      <section className="hero">
        <div className="hero-wash" />
        {/* made-up people connecting over the map; fades out with the start page */}
        {getMap && <LandingNetwork getMap={getMap} mobile={mobile} />}
        <motion.header className="landing-head" initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={spring}>
          <Brand size="lg" onHome={() => scroller.current?.scrollTo({ top: 0, behavior: 'smooth' })} />
          <nav className="landing-nav">
            <button onClick={() => onEnter({})}>{t('Map')}</button>
            <span className="landing-lang">
              <button className={lang === 'pl' ? 'on' : ''} onClick={() => setLang('pl')} aria-label="Polski"><FlagPL size={20} />PL</button>
              <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')} aria-label="English"><FlagUK size={20} />EN</button>
            </span>
          </nav>
        </motion.header>

        <div className="hero-center" ref={center}>
          <motion.h1 initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -24 }} transition={{ ...spring, delay: 0.05 }}>
            {t("What's the plan in Warsaw today?")}
          </motion.h1>
          <LandingSearch features={features} onSearch={onEnter} />
          <div className="tiles-block">{/* the big tiles + the More row, one item in the hero column */}
            <motion.div className="hero-tiles" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} transition={{ ...spring, delay: 0.12 }}>
              {/* phones: just the first two + More, so three fit in one row */}
              {TILES.filter((tile, i) => !mobile || i < 2 || tile.more).map((tile, i) => (
                <Tile key={tile.label} tile={tile} delay={0.15 + i * 0.04} open={more}
                  onClick={() => (tile.more ? setMore((m) => !m) : onEnter({ category: tile.category, label: t(tile.label), people: tile.people }))} />
              ))}
            </motion.div>
            <MoreTiles open={more} onPick={(slug) => onEnter({ category: slug, label: categoryLabel(slug) })} />
          </div>
        </div>
        <motion.button className="hero-more" onClick={() => document.getElementById('syrenka-selects')?.scrollIntoView({ behavior: 'smooth' })}
          initial={{ opacity: 0 }} animate={{ opacity: 1, y: [0, 6, 0] }} transition={{ delay: 0.6, y: { repeat: Infinity, duration: 2.2 } }}>
          {t('Syrenka Selects')} ↓
        </motion.button>
      </section>

      <section className="selects" id="syrenka-selects">
        {/* tap: the picks slide up to the top of the screen, this button just past it */}
        <motion.button className="selects-head" onClick={showSelects} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-20px' }} transition={spring}>
          <h2>{t('Syrenka Selects')}</h2>
        </motion.button>
        <div className="selects-grid" ref={grid}>
          {loading && Array.from({ length: 6 }).map((_, i) => <div key={i} className={`sel-card skeleton ${i === 2 ? 'wide' : ''}`} />)}
          {!loading && !selects.length && <p className="selects-empty">{t('Nothing picked yet. Open the map to see everything.')}</p>}
          {selects.map(({ feature: f, wide, going, asked, userMade }, i) => {
            const p = f.properties
            const cat = p.categories?.[0]
            return (
              <motion.button key={p.event_id} className={`sel-card ${wide ? 'wide' : ''}`} onClick={() => onEnter({ feature: f })}
                initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ ...spring, delay: (i % 4) * 0.05 }}>
                <div className="sel-img" style={p.image_url ? {} : { background: `linear-gradient(135deg, ${categoryColor(cat)}, color-mix(in srgb, ${categoryColor(cat)} 40%, #fff))` }}>
                  {p.image_url && <img className="sel-photo" src={secureImage(p.image_url)} alt="" loading="lazy" onError={() => setBroken((b) => new Set(b).add(p.event_id))} />}
                  <span className="sel-cat" style={{ color: typeColor(typeOf(p)) }}>{typeLabel(typeOf(p))}</span>
                  {userMade && <span className="sel-people"><Users size={13} /> {t('Made by people')}</span>}
                  {(going || asked) && <span className="sel-you">{t(going ? "You're going" : 'Asked to join')}</span>}
                </div>
                <div className="sel-body">
                  <div className="sel-when">{fmtWhen(p.starts_at)}{p.venue_name ? ` · ${p.venue_name}` : ''}</div>
                  <h3>{p.title}</h3>
                  {wide && p.lead && <p className="sel-lead">{p.lead}</p>}
                  {p.district && <div className="sel-where">{p.district}</div>}
                </div>
              </motion.button>
            )
          })}
        </div>
        <div className="selects-foot">
          <button className="btn primary" onClick={() => onEnter({})}>{t('Open the map')}</button>
        </div>
      </section>

      <footer className="landing-foot">
        <span>syrenka.me · Warszawa</span>
        <span>{t('Data: Warsaw Open Data, OpenStreetMap')}</span>
      </footer>
    </motion.div>
  )
}
