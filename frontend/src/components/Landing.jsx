import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { CATEGORIES, categoryColor, categoryLabel } from '../data/categories'
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

function Tile({ tile, onClick, small, delay = 0, open }) {
  const { t } = useLang()
  const c = tile.more ? 'var(--fg)' : categoryColor(tile.category)
  const I = tile.Icon
  return (
    <motion.button className={`hero-tile ${tile.people ? 'people' : ''} ${tile.more ? 'more' : ''} ${small ? 'small' : ''}`} style={{ '--c': c }} onClick={onClick}
      layout initial={{ opacity: 0, y: 14, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
      transition={{ type: 'spring', stiffness: 420, damping: 28, delay }} whileHover={{ y: -3, scale: 1.03 }} whileTap={{ scale: 0.96 }}>
      <span className="tile-ic">{I && <I size={small ? 16 : 20} />}</span>
      {tile.people && <span className="tile-people" title={t('Made by people like you')}><Users size={14} /></span>}
      <span className="tile-label">{t(tile.label)}</span>
      {tile.more && <motion.span className="tile-chev" animate={{ rotate: open ? 180 : 0 }}><Chevron size={16} /></motion.span>}
    </motion.button>
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
  const allCats = Object.keys(CATEGORIES).filter((slug) => slug !== 'other')

  // Keep the search pill in the middle of the screen: the space above the headline is whatever puts the
  // pill's centre at half the viewport. Syrenka Selects follows the tiles directly, so its first cards
  // peek in at the bottom. Re-measured when the headline / pill change size or the window resizes.
  const center = useRef(null)
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
            <button onClick={() => document.getElementById('syrenka-selects')?.scrollIntoView({ behavior: 'smooth' })}>{t('Syrenka Selects')}</button>
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
          <LandingSearch layoutId="search-pill" features={features} onSearch={onEnter} />
          <motion.div className="hero-tiles" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} transition={{ ...spring, delay: 0.12 }}>
            {TILES.map((tile, i) => (
              <Tile key={tile.label} tile={tile} delay={0.15 + i * 0.04} open={more}
                onClick={() => (tile.more ? setMore((m) => !m) : onEnter({ category: tile.category, label: t(tile.label), people: tile.people }))} />
            ))}
          </motion.div>
          <AnimatePresence>
            {more && (
              <motion.div className="hero-tiles all" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}>
                {allCats.map((slug, i) => (
                  <Tile key={slug} small delay={i * 0.025} tile={{ label: CATEGORIES[slug].label, category: slug }}
                    onClick={() => onEnter({ category: slug, label: categoryLabel(slug) })} />
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <motion.button className="hero-more" onClick={() => document.getElementById('syrenka-selects')?.scrollIntoView({ behavior: 'smooth' })}
          initial={{ opacity: 0 }} animate={{ opacity: 1, y: [0, 6, 0] }} transition={{ delay: 0.6, y: { repeat: Infinity, duration: 2.2 } }}>
          {t('Syrenka Selects')} ↓
        </motion.button>
      </section>

      <section className="selects" id="syrenka-selects">
        <motion.div className="selects-head" initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-20px' }} transition={spring}>
          <h2>{t('Syrenka Selects')}</h2>
        </motion.div>
        <div className="selects-grid">
          {loading && Array.from({ length: 6 }).map((_, i) => <div key={i} className={`sel-card skeleton ${i === 0 ? 'wide' : ''}`} />)}
          {!loading && !selects.length && <p className="selects-empty">{t('Nothing picked yet. Open the map to see everything.')}</p>}
          {selects.map(({ feature: f, wide, going, asked, userMade }, i) => {
            const p = f.properties
            const cat = p.categories?.[0]
            return (
              <motion.button key={p.event_id} className={`sel-card ${wide ? 'wide' : ''}`} onClick={() => onEnter({ feature: f })}
                initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ ...spring, delay: (i % 4) * 0.05 }}>
                <div className="sel-img" style={p.image_url ? {} : { background: `linear-gradient(135deg, ${categoryColor(cat)}, color-mix(in srgb, ${categoryColor(cat)} 40%, #fff))` }}>
                  {p.image_url && <img className="sel-photo" src={secureImage(p.image_url)} alt="" loading="lazy" onError={() => setBroken((b) => new Set(b).add(p.event_id))} />}
                  <span className="sel-cat" style={{ color: categoryColor(cat) }}>{categoryLabel(cat)}</span>
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
