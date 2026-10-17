import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { assetUrl, fetchMe, isLoggedIn, onAuthChange } from '../data/api'
import { useLang } from '../i18n'
import { usePopover } from './Calendar'
import { LoginForm } from './LoginForm'

/**
 * Far top right, on every screen (start page, map, full-screen slide-over). Logged out: "Log in", which
 * opens a small white card with email + password. Logged in: a pill with your photo and name; tapping it
 * opens your profile. Its width is published as --account-w so the controls next to it make room.
 */
export function AccountButton({ onProfile, view }) {
  const { t } = useLang()
  const spring = useSpring()
  const { open, setOpen, ref } = usePopover()
  const [me, setMe] = useState(null)
  const [loggedIn, setLoggedIn] = useState(isLoggedIn)

  useEffect(() => {
    const load = () => { const on = isLoggedIn(); setLoggedIn(on); if (on) fetchMe().then(setMe); else setMe(null) }
    load()
    return onAuthChange(load)
  }, [])

  // publish the width so the editor toggle / slide-over actions sit to its left
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const root = document.documentElement
    const ro = new ResizeObserver(() => root.style.setProperty('--account-w', `${el.offsetWidth}px`))
    ro.observe(el)
    return () => { ro.disconnect(); root.style.removeProperty('--account-w') }
  }, [ref])

  const name = me?.display_name || (loggedIn ? '…' : '')
  const photo = me?.photos?.[0]

  return (
    <div className={`account on-${view}`} ref={ref}>
      {loggedIn ? (
        <motion.button className="account-pill surface" onClick={onProfile} title={t('Your profile')} layout transition={spring}>
          <span className="account-av" style={photo ? { backgroundImage: `url(${assetUrl(photo)})` } : {}}>{!photo && (name[0] || '?').toUpperCase()}</span>
          <span className="account-name">{name}</span>
        </motion.button>
      ) : (
        <button className={`account-login ${open ? 'open' : ''}`} onClick={() => setOpen(!open)} aria-expanded={open}>{t('Log in')}</button>
      )}
      <AnimatePresence>
        {open && !loggedIn && (
          <motion.div className="account-card surface" initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }} transition={spring}>
            <LoginForm compact onDone={() => setOpen(false)} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
