import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { categoryColor, categoryLabel } from '../data/categories'
import { typeColor, typeLabel, typeOf } from '../data/types'
import { useLang } from '../i18n'
import { pickSelects, secureImage } from '../landing/selects'
import { useSocial } from '../data/social'
import { fmtWhen } from '../mapboxes/curate'
import { CloseButton } from './CloseButton'
import { Mermaid } from './Icons'

/**
 * "Syrenka poleca" in the right-hand bar, opened by the mermaid button next to the search bar.
 * Same picks as the start page: headliners get a big photo, the rest are compact rows.
 */
/** single: one column of full posters (the slide-over tray's "1 wide" view). */
export function SelectsRail({ features, onPick, onClose, inSheet = false, single = false }) {
  const { t } = useLang()
  const spring = useSpring()
  const social = useSocial()
  const selects = useMemo(() => pickSelects(features, { social }), [features, social])
  return (
    <motion.section className={`selects-rail ${inSheet ? 'in-sheet' : 'surface'} ${single ? 'single' : ''}`} layout
      initial={{ opacity: 0, x: 24, scale: 0.97 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: 24, scale: 0.97 }} transition={spring}>
      <header className="sr-head">
        <Mermaid size={22} />
        <div><h2>{t('Syrenka Selects')}</h2><div className="mb-sub">{t('Next two weeks, picked from real events')}</div></div>
        {onClose && <CloseButton size={34} onClick={onClose} />}
      </header>
      <div className="sr-list">
        {!selects.length && <p className="res-empty">{t('Nothing picked yet. Open the map to see everything.')}</p>}
        {selects.map(({ feature: f, wide: headliner, going, asked }) => {
          const wide = single || headliner
          const p = f.properties
          const cat = p.categories?.[0]
          const img = p.image_url ? { backgroundImage: `url(${secureImage(p.image_url)})` } : { background: categoryColor(cat) }
          return (
            <button key={p.event_id} className={`sr-item ${wide ? 'wide' : ''}`} onClick={() => onPick(f)}>
              <span className="sr-img" style={img}>{wide && <span className="sel-cat" style={{ color: typeColor(typeOf(p)) }}>{typeLabel(typeOf(p))}</span>}</span>
              <span className="sr-text">
                <span className="sr-when">{fmtWhen(p.starts_at)}{!wide ? <> · <b style={{ color: typeColor(typeOf(p)) }}>{typeLabel(typeOf(p))}</b></> : null}</span>
                <span className="sr-title">{p.title}</span>
                {(going || asked) && <span className="sr-you">{t(going ? "You're going" : 'Asked to join')}</span>}
                {p.venue_name && <span className="sr-where">{p.venue_name}</span>}
              </span>
            </button>
          )
        })}
      </div>
    </motion.section>
  )
}
