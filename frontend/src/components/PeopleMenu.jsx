import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useConfig, useSpring } from '../config/store'
import { isLoggedIn, LoginRequired, onAuthChange } from '../data/api'
import { refreshPeople, shareArea, usePeople } from '../data/people'
import { useLang } from '../i18n'
import { Users } from './Icons'
import { LoginForm } from './LoginForm'

const RESEND_MS = 10 * 60_000 // a shared area goes stale after 6 h without news (backend/app/routers/people.py)

/**
 * Toolbar "People" button, next to the pins: a box slides up with
 *   - People: the pulsing pins of everyone sharing their area (config `showPeople`)
 *   - Share my area: put my own pin out there, roughly where I am, so friends can come and hang out
 * (Their open invitations are pins in "New friends", in the pin box.)
 */
export function PeopleMenu({ me }) {
  const { values, set } = useConfig()
  const { t } = useLang()
  const spring = useSpring()
  const { people, mine } = usePeople()
  const [open, setOpen] = useState(false)
  const [needLogin, setNeedLogin] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const ref = useRef(null)
  const showing = values.showPeople !== false
  const sharing = Boolean(mine?.share)
  const others = people.filter((p) => !p.is_self).length

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  useEffect(() => onAuthChange(() => { if (isLoggedIn()) setNeedLogin(false); refreshPeople() }), [])

  // while sharing, keep my area fresh (and following me) as long as the app is open
  useEffect(() => {
    if (!sharing || !me) return
    const id = setInterval(() => shareArea(true, me).catch(() => {}), RESEND_MS)
    return () => clearInterval(id)
  }, [sharing, me])

  async function toggleShare() {
    if (!isLoggedIn()) { setNeedLogin(true); return }
    setBusy(true); setErr(null)
    try {
      await shareArea(!sharing, me)
      if (!sharing && !showing) set('showPeople', true) // you'll want to see yourself among the others
    } catch (e) {
      if (e instanceof LoginRequired) setNeedLogin(true)
      else setErr(t(!me ? 'We don’t know where you are yet' : 'Could not save, try again'))
    } finally { setBusy(false) }
  }

  return (
    <div className="pinmenu peoplemenu" ref={ref}>
      <AnimatePresence>
        {open && (
          <motion.div className="pin-menu people-menu surface" role="menu" aria-label={t('People')}
            initial={{ opacity: 0, y: 16, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.95 }} transition={spring}>
            <div className="pm-title">{t('People')}</div>
            <button role="menuitemcheckbox" aria-checked={showing} className={`pm-opt ${showing ? 'on' : ''}`} onClick={() => set('showPeople', !showing)}>
              <span className="pm-emoji" aria-hidden="true">👋</span>
              <span className="pm-label">{t('People around')}{others > 0 && <span className="pm-count">{others}</span>}</span>
              <span className={`ctl-toggle ${showing ? 'on' : ''}`} aria-hidden="true"><span className="ctl-knob" /></span>
            </button>
            <button role="menuitemcheckbox" aria-checked={sharing} className={`pm-opt ${sharing ? 'on' : ''}`} onClick={toggleShare} disabled={busy}>
              <span className="pm-emoji" aria-hidden="true">📡</span>
              <span className="pm-label">{t('Share my area')}</span>
              <span className={`ctl-toggle ${sharing ? 'on' : ''}`} aria-hidden="true"><span className="ctl-knob" /></span>
            </button>
            <p className="people-hint">
              {sharing ? t('Your pin is out: people see roughly where you are (about 100 m), so friends can come and hang out.')
                : t('Put a pin out roughly where you are (about 100 m, never the exact spot) to invite friends to hang out.')}
            </p>
            {err && <p className="people-hint err">{err}</p>}
            {needLogin && !isLoggedIn() && <div className="people-login"><LoginForm compact intro={t('Log in to share your area.')} onDone={() => setNeedLogin(false)} /></div>}
          </motion.div>
        )}
      </AnimatePresence>
      <button className={`tb pin-btn people-btn ${open ? 'open' : ''} ${showing ? 'live' : ''}`} onClick={() => setOpen(!open)} title={t('People')} aria-haspopup="menu" aria-expanded={open}>
        <Users size={20} />
        <small>{t('People')}</small>
      </button>
    </div>
  )
}
