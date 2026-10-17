import { useEffect, useId, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { useLang } from '../i18n'

/** Round flag badges. Each instance gets its own clipPath id so several can share a page. */
export function FlagPL({ size = 22 }) {
  const id = useId()
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden="true">
      <clipPath id={id}><circle cx="15" cy="15" r="15" /></clipPath>
      <g clipPath={`url(#${id})`}><rect width="30" height="15" fill="#fff" /><rect y="15" width="30" height="15" fill="#DC143C" /></g>
      <circle cx="15" cy="15" r="14.7" fill="none" stroke="#0003" strokeWidth=".6" />
    </svg>
  )
}

export function FlagUK({ size = 22 }) {
  const id = useId()
  return (
    <svg width={size} height={size} viewBox="15 0 30 30" aria-hidden="true">
      <clipPath id={id}><circle cx="30" cy="15" r="15" /></clipPath>
      <g clipPath={`url(#${id})`}>
        <rect width="60" height="30" fill="#012169" />
        <path d="M0,0 60,30M60,0 0,30" stroke="#fff" strokeWidth="6" />
        <path d="M0,0 60,30M60,0 0,30" stroke="#C8102E" strokeWidth="2" />
        <path d="M30,0v30M0,15h60" stroke="#fff" strokeWidth="10" />
        <path d="M30,0v30M0,15h60" stroke="#C8102E" strokeWidth="6" />
      </g>
    </svg>
  )
}

const LANGS = [['pl', 'PL', FlagPL], ['en', 'EN', FlagUK]]

/** Far-right toolbar button: tap -> a small box slides up with PL / EN; picking one (or tapping away) closes it. */
export function LangSwitch() {
  const { lang, setLang, t } = useLang()
  const spring = useSpring()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const [, code, Flag] = LANGS.find(([l]) => l === lang)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div className="lang" ref={ref}>
      <AnimatePresence>
        {open && (
          <motion.div className="lang-menu surface" role="menu" aria-label={t('Language')}
            initial={{ opacity: 0, y: 16, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.9 }} transition={spring}>
            {LANGS.map(([l, label, F]) => (
              <button key={l} role="menuitemradio" aria-checked={lang === l} className={`lang-opt ${lang === l ? 'on' : ''}`}
                onClick={() => { setLang(l); setOpen(false) }}>
                <F size={22} />{label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      <button className={`tb lang-btn ${open ? 'open' : ''}`} onClick={() => setOpen(!open)} title={t('Language')} aria-haspopup="menu" aria-expanded={open}>
        <span className="lang-face"><Flag size={20} /><b>{code}</b></span>
        <small>{t('Language')}</small>
      </button>
    </div>
  )
}
