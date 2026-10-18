import { motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { CloseButton } from './CloseButton'
import { Bike, FACT_ICON, Message, Plus, Star, Ticket, Walk } from './Icons'
import { categoryColor } from '../data/categories'
import { fmtWhen } from '../mapboxes/curate'
import { useLang } from '../i18n'
import { askToJoin, toggleGoing, useSocial } from '../data/social'
import { chatTarget } from '../data/chat'

const AV_COLORS = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']

function Block({ b, feature }) {
  const { t } = useLang()
  const social = useSocial()
  switch (b.type) {
    case 'facts':
      return <div className="blk facts">{b.items.map((it, i) => { const I = FACT_ICON[it.icon]; return <div className="fact" key={i}>{I && <I size={15} />}<span>{it.text}</span></div> })}</div>
    case 'posters':
      return (
        <div className="blk">
          <div className="blk-title"><Ticket size={12} style={{ verticalAlign: '-2px' }} /> {t('Upcoming here')}</div>
          <div className="poster-strip">
            {b.items.map((t, i) => (
              <a className="poster" key={i} href={t.url || '#'} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none' }}>
                <div className="pimg" style={t.image_url ? { backgroundImage: `url(${t.image_url})` } : {}}>
                  {t.price != null && <span className="price">{t.price} {t.currency || 'zł'}</span>}
                  {t.availability === 'SoldOut' && <span className="sold">{t('SOLD OUT')}</span>}
                </div>
                <div className="pt">{t.title}</div>
                <div className="pd">{fmtWhen(t.starts_at)}</div>
              </a>
            ))}
          </div>
        </div>
      )
    case 'social': {
      const id = String(feature.properties.event_id)
      const going = Boolean(social.going[id]), asked = Boolean(social.joined[id])
      const isInvite = Boolean(feature.properties.is_public_invite || feature.properties.audience)
      const n = (b.attendees || 0) + (going ? 1 : 0)
      const act = async () => {
        if (isInvite) { const r = await askToJoin(feature); window.dispatchEvent(new CustomEvent('syrenka:toast', { detail: t(r.needsLogin ? 'Asked to join · log in so the host can answer you' : 'Asked to join · the host will get back to you') })) }
        else { const r = await toggleGoing(feature); window.dispatchEvent(new CustomEvent('syrenka:toast', { detail: t(r.on ? "You're going · it now counts in Syrenka Selects" : 'Not going anymore') })) }
      }
      return (
        <div className={`blk social ${going || asked ? 'on' : ''}`}>
          {/* only real people: the host's initial; attendee avatars come once the API lists them */}
          {b.host && <div className="avatars"><span className="av" style={{ background: AV_COLORS[0] }}>{b.host[0]}</span></div>}
          <div className="txt">
            {b.host && <><b>{b.host}</b> {t('is hosting')} · </>}
            {n ? <><b>{n}</b> {t('going')}</> : <>{t('Be the first to go')}</>}
            {b.wanting ? <>, <b>{b.wanting}</b> {t('looking for company')}</> : null}
            {b.seats != null && <> · <b>{b.seats}</b> {t(b.seats === 1 ? 'seat left' : 'seats left')}</>}
            {going && <> · <b className="you">{t("you're going")}</b></>}
            {asked && <> · <b className="you">{t('asked to join')}</b></>}
          </div>
          <button className={`btn small ${going || asked ? '' : 'primary'}`} onClick={act} disabled={asked}>
            {isInvite ? (asked ? t('Asked ✓') : b.cta) : going ? t('Going ✓') : b.cta}
          </button>
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
          <div className="blk-title">{t('Pitches available')}</div>
          <div className="pitch-grid">
            {(b.equipment.length ? b.equipment : ['boisko']).map((e, i) => <span className="pitch-chip open" key={i}>● {e.replace('boiska do ', '').replace('boiska ', '')}</span>)}
            {b.surface && <span className="pitch-chip">{t('surface')}: {b.surface}</span>}
            <span className={`pitch-chip ${b.today ? 'open' : ''}`}>{b.today ? `${t('today')} ${b.today.replace('Od ', '').replace(' do ', '–')}` : t('closed today')}</span>
          </div>
          {b.approx && <div className="mb-text muted" style={{ marginTop: 8 }}>{t('Location approximate (source has no coordinates yet).')}</div>}
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
export function MapBox({ data, feature, expanded, journey, onClose, onExpand, starred, onStar, onChat, showImage = true, layoutId }) {
  const spring = useSpring()
  const { t } = useLang()
  const c = categoryColor(feature.properties.categories?.[0])
  return (
    <motion.article className={`mapbox surface ${expanded ? 'expanded' : ''}`} layout layoutId={layoutId}
      initial={{ opacity: 0, scale: 0.85, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9, y: 8 }} transition={spring}>
      {onClose && <CloseButton size={34} className="mb-x" onClick={onClose} />}
      {onStar && <button className={`btn icon small mb-star ${starred ? 'on' : ''}`} onClick={onStar} aria-label={t('Star')}><Star size={16} filled={starred} /></button>}
      {showImage && data.image && <div className="mb-img" style={{ backgroundImage: `url(${data.image})` }} />}
      {showImage && !data.image && <div className="mb-img" style={{ height: 8, background: `linear-gradient(90deg, ${c}, color-mix(in srgb, ${c} 30%, transparent))` }} />}
      <div className="mb-body">
        <div className="mb-head">
          <div style={{ flex: 1 }}>
            <h2>{data.title}</h2>
            {data.subtitle && <div className="mb-sub">{data.subtitle}</div>}
            {feature.properties.translated && (
              <div className="mb-translated" title={[feature.properties.original?.title, feature.properties.original?.lead].filter(Boolean).join('\n\n')}>
                {t('Translated automatically · original in {lang}', { lang: t(feature.properties.original?.lang === 'pl' ? 'Polish' : feature.properties.original?.lang === 'en' ? 'English' : 'another language') })}
              </div>
            )}
          </div>
        </div>
        <div className="mb-badges">
          {data.badges.map((b, i) => <span className={`badge ${i === 0 ? 'accent' : ''}`} key={i} style={i === 0 ? { background: `color-mix(in srgb, ${c} 15%, transparent)`, color: c } : {}}>{b}</span>)}
          {onChat && chatTarget(feature) && (
            <button className="badge mb-chat" onClick={() => onChat(chatTarget(feature))} title={t('Talk with people going')}><Message size={13} stroke={2.2} /> {t('Chat')}</button>
          )}
        </div>
        {journey && (
          <div className={`blk journey ${journey.pending ? 'pending' : ''}`}>
            <span className="j"><Walk size={18} />{journey.pending ? t('pinging…') : t('{n}m walking', { n: journey.walkMin })}</span>
            <span className="j"><Bike size={18} />{journey.pending ? '' : t('{n}m cycling', { n: journey.bikeMin })}</span>
            {!journey.pending && <span className="src">{journey.km.toFixed(1)} km · {t(journey.source === 'osrm' ? 'streets' : 'estimate')}</span>}
          </div>
        )}
        {data.blocks.slice(0, expanded ? 99 : 3).map((b, i) => <Block b={b} feature={feature} key={i} />)}
        {expanded && data.url && <a className="mb-link" href={data.url} target="_blank" rel="noreferrer">{t('Open source page ↗')}</a>}
        {expanded && (
          <div className="blk">
            <div className="blk-title">{t('Everything we know')}</div>
            <pre style={{ fontSize: 11, color: 'var(--fg-3)', whiteSpace: 'pre-wrap', fontFamily: 'JetBrains Mono, monospace' }}>
              {JSON.stringify({ ...feature.properties, upcoming: undefined }, null, 1).slice(0, 1600)}
            </pre>
          </div>
        )}
        {!expanded && <div className="mb-foot" />}
      </div>
      {onExpand && !expanded && <button className="btn icon small primary mb-plus" onClick={onExpand} aria-label={t('Expand')}><Plus size={16} /></button>}
    </motion.article>
  )
}
