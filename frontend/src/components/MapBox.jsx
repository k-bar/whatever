import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { Bike, FACT_ICON, Plus, Star, Ticket, Walk, X } from './Icons'
import { categoryColor } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'

const AV_COLORS = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']

function Block({ b }) {
  switch (b.type) {
    case 'facts':
      return <div className="blk facts">{b.items.map((it, i) => { const I = FACT_ICON[it.icon]; return <div className="fact" key={i}>{I && <I size={15} />}<span>{it.text}</span></div> })}</div>
    case 'posters':
      return (
        <div className="blk">
          <div className="blk-title"><Ticket size={12} style={{ verticalAlign: '-2px' }} /> Upcoming here</div>
          <div className="poster-strip">
            {b.items.map((t, i) => (
              <a className="poster" key={i} href={t.url || '#'} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none' }}>
                <div className="pimg" style={t.image_url ? { backgroundImage: `url(${t.image_url})` } : {}}>
                  {t.price != null && <span className="price">{t.price} {t.currency || 'zł'}</span>}
                  {t.availability === 'SoldOut' && <span className="sold">SOLD OUT</span>}
                </div>
                <div className="pt">{t.title}</div>
                <div className="pd">{fmtWhen(t.starts_at)}</div>
              </a>
            ))}
          </div>
        </div>
      )
    case 'social': {
      const n = b.attendees || 0
      return (
        <div className="blk social">
          <div className="avatars">
            {Array.from({ length: Math.min(3, Math.max(1, n)) }).map((_, i) => (
              <span className="av" key={i} style={{ background: AV_COLORS[i % AV_COLORS.length] }}>{b.host && i === 0 ? b.host[0] : String.fromCharCode(65 + ((i * 7) % 26))}</span>
            ))}
          </div>
          <div className="txt">
            {b.host && <><b>{b.host}</b> is hosting · </>}
            {n ? <><b>{n}</b> going</> : <>Be the first to go</>}
            {b.wanting ? <>, <b>{b.wanting}</b> looking for company</> : null}
            {b.seats != null && <> · <b>{b.seats}</b> seat{b.seats === 1 ? '' : 's'} left</>}
          </div>
          <button className="btn small primary">{b.cta}</button>
        </div>
      )
    }
    case 'live':
      return <div className={`blk live ${b.level}`}><span className="ldot" />{b.text}</div>
    case 'hours':
      return <div className="blk facts"><div className="fact">{FACT_ICON.clock({ size: 15 })}<span>{b.text}</span></div></div>
    case 'pitch':
      return (
        <div className="blk">
          <div className="blk-title">Pitches available</div>
          <div className="pitch-grid">
            {(b.equipment.length ? b.equipment : ['boisko']).map((e, i) => <span className="pitch-chip open" key={i}>● {e.replace('boiska do ', '').replace('boiska ', '')}</span>)}
            {b.surface && <span className="pitch-chip">surface: {b.surface}</span>}
            <span className={`pitch-chip ${b.today ? 'open' : ''}`}>{b.today ? `today ${b.today.replace('Od ', '').replace(' do ', '–')}` : 'closed today'}</span>
          </div>
          {b.approx && <div className="mb-text muted" style={{ marginTop: 8 }}>Location approximate (source has no coordinates yet).</div>}
        </div>
      )
    case 'text':
      return <p className={`blk mb-text ${b.muted ? 'muted' : ''}`}>{b.text}</p>
    default:
      return null
  }
}

/**
 * One map info box. `data` comes from curate(); `expanded` turns it into the right-side panel.
 */
export function MapBox({ data, feature, expanded, journey, onClose, onExpand, starred, onStar, showImage = true, layoutId }) {
  const spring = useSpring()
  const c = categoryColor(feature.properties.categories?.[0])
  return (
    <motion.article className={`mapbox surface ${expanded ? 'expanded' : ''}`} layout layoutId={layoutId}
      initial={{ opacity: 0, scale: 0.85, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9, y: 8 }} transition={spring}>
      {onClose && <button className="btn icon small mb-x" onClick={onClose} aria-label="Close"><X size={24} stroke={2.4} /></button>}
      {onStar && <button className={`btn icon small mb-star ${starred ? 'on' : ''}`} onClick={onStar} aria-label="Star"><Star size={16} filled={starred} /></button>}
      {showImage && data.image && <div className="mb-img" style={{ backgroundImage: `url(${data.image})` }} />}
      {showImage && !data.image && <div className="mb-img" style={{ height: 8, background: `linear-gradient(90deg, ${c}, color-mix(in srgb, ${c} 30%, transparent))` }} />}
      <div className="mb-body">
        <div className="mb-head">
          <div style={{ flex: 1 }}>
            <h2>{data.title}</h2>
            {data.subtitle && <div className="mb-sub">{data.subtitle}</div>}
          </div>
        </div>
        <div className="mb-badges">
          {data.badges.map((b, i) => <span className={`badge ${i === 0 ? 'accent' : ''}`} key={i} style={i === 0 ? { background: `color-mix(in srgb, ${c} 15%, transparent)`, color: c } : {}}>{b}</span>)}
        </div>
        {journey && (
          <div className={`blk journey ${journey.pending ? 'pending' : ''}`}>
            <span className="j"><Walk size={18} />{journey.pending ? 'pinging…' : `${journey.walkMin}m walking`}</span>
            <span className="j"><Bike size={18} />{journey.pending ? '' : `${journey.bikeMin}m cycling`}</span>
            {!journey.pending && <span className="src">{journey.km.toFixed(1)} km · {journey.source === 'osrm' ? 'streets' : 'estimate'}</span>}
          </div>
        )}
        {data.blocks.slice(0, expanded ? 99 : 3).map((b, i) => <Block b={b} key={i} />)}
        {expanded && data.url && <a className="mb-link" href={data.url} target="_blank" rel="noreferrer">Open source page ↗</a>}
        {expanded && (
          <div className="blk">
            <div className="blk-title">Everything we know</div>
            <pre style={{ fontSize: 11, color: 'var(--fg-3)', whiteSpace: 'pre-wrap', fontFamily: 'JetBrains Mono, monospace' }}>
              {JSON.stringify({ ...feature.properties, upcoming: undefined }, null, 1).slice(0, 1600)}
            </pre>
          </div>
        )}
        {!expanded && <div className="mb-foot" />}
      </div>
      {onExpand && !expanded && <button className="btn icon small primary mb-plus" onClick={onExpand} aria-label="Expand"><Plus size={16} /></button>}
    </motion.article>
  )
}
