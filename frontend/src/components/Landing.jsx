import { useMemo, useRef } from 'react'
import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { categoryColor, categoryLabel } from '../data/categories'
import { useLang } from '../i18n'
import { pickSelects, secureImage } from '../landing/selects'
import { fmtWhen } from '../mapboxes/curate'
import { Brand } from './Brand'
import { LandingSearch } from './LandingSearch'
import { FlagPL, FlagUK } from './LangSwitch'

const CHIPS = [
  { label: 'Today', window: 'today' }, { label: 'This weekend', window: 'weekend' },
  { label: 'Concerts', category: 'music' }, { label: 'For kids', category: 'family' },
  { label: 'Cinema', category: 'film' }, { label: 'Exhibitions', category: 'exhibitions' },
]

/**
 * The start page ("Search"): headline + big search over the live map (washed out), quick chips, and
 * "Syrenka poleca" below. Nothing here reloads the map: entering just fades the wash away while the
 * search pill (shared layoutId "search-pill") flies to its top-left spot on the map.
 */
export function Landing({ features, onEnter }) {
  const { t, lang, setLang } = useLang()
  const spring = useSpring()
  const scroller = useRef(null)
  const selects = useMemo(() => pickSelects(features), [features])
  const loading = !features

  return (
    <motion.div className="landing" ref={scroller} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.65, ease: 'easeInOut' } }}>
      <section className="hero">
        <div className="hero-wash" />
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

        <div className="hero-center">
          <motion.h1 initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -24 }} transition={{ ...spring, delay: 0.05 }}>
            {t("What's the plan in Warsaw today?")}
          </motion.h1>
          <LandingSearch layoutId="search-pill" features={features} onSearch={onEnter} />
          <motion.div className="hero-chips" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} transition={{ ...spring, delay: 0.12 }}>
            {CHIPS.map((c, i) => (
              <button key={c.label} className={`hero-chip ${i % 2 ? 'warm' : 'cool'}`} onClick={() => onEnter({ window: c.window, category: c.category, label: t(c.label) })}>{t(c.label)}</button>
            ))}
          </motion.div>
        </div>
        <motion.button className="hero-more" onClick={() => document.getElementById('syrenka-selects')?.scrollIntoView({ behavior: 'smooth' })}
          initial={{ opacity: 0 }} animate={{ opacity: 1, y: [0, 6, 0] }} transition={{ delay: 0.6, y: { repeat: Infinity, duration: 2.2 } }}>
          {t('Syrenka Selects')} ↓
        </motion.button>
      </section>

      <section className="selects" id="syrenka-selects">
        <div className="selects-head">
          <h2>{t('Syrenka Selects')}</h2>
          <p>{t('The best of Warsaw in the next two weeks, picked automatically from real events.')}</p>
        </div>
        <div className="selects-grid">
          {loading && Array.from({ length: 6 }).map((_, i) => <div key={i} className={`sel-card skeleton ${i === 0 ? 'wide' : ''}`} />)}
          {!loading && !selects.length && <p className="selects-empty">{t('Nothing picked yet. Open the map to see everything.')}</p>}
          {selects.map(({ feature: f, wide }, i) => {
            const p = f.properties
            const cat = p.categories?.[0]
            return (
              <motion.button key={p.event_id} className={`sel-card ${wide ? 'wide' : ''}`} onClick={() => onEnter({ feature: f })}
                initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ ...spring, delay: (i % 4) * 0.05 }}>
                <div className="sel-img" style={p.image_url ? { backgroundImage: `url(${secureImage(p.image_url)})` } : { background: `linear-gradient(135deg, ${categoryColor(cat)}, color-mix(in srgb, ${categoryColor(cat)} 40%, #fff))` }}>
                  <span className="sel-cat" style={{ color: categoryColor(cat) }}>{categoryLabel(cat)}</span>
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
