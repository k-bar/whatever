import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import {
  changeEmail, changePassword, fetchMe, logout, logoutEverywhere, onAuthChange, resendVerification, resetPassword, verifyEmail,
} from '../data/api'
import { useLang } from '../i18n'
import { Check, X } from './Icons'

/** My account (GET /me), refreshed on log in / out and when the email gets confirmed. */
export function useMe() {
  const [me, setMe] = useState(undefined) // undefined = loading, null = logged out
  useEffect(() => {
    const load = () => fetchMe().then(setMe)
    load()
    return onAuthChange(load)
  }, [])
  return me
}

/**
 * "Confirm your email" with a resend button. Shown wherever a locked feature lives (profile, chats,
 * create event) while the account isn't confirmed; renders nothing otherwise.
 */
export function VerifyBanner({ me, compact = false }) {
  const { t } = useLang()
  const [state, setState] = useState(null) // null | sending | sent | error message
  if (!me || me.email_verified) return null
  const resend = async () => {
    setState('sending')
    try { await resendVerification(); setState('sent') } catch (e) { setState(t(e.message)) }
  }
  return (
    <div className={`verify-banner ${compact ? 'compact' : ''}`} role="status">
      <span className="vb-ic" aria-hidden>✉</span>
      <div className="vb-txt">
        <b>{t('Confirm your email')}</b>
        <span>{state === 'sent'
          ? t('Sent again to {email}. Check spam too.', { email: me.email })
          : t('Open the link we sent to {email} to add friends, create events and chat.', { email: me.email })}</span>
        {state && state !== 'sent' && state !== 'sending' && <span className="vb-err">{state}</span>}
      </div>
      {state !== 'sent' && <button className="btn small" disabled={state === 'sending'} onClick={resend}>{t(state === 'sending' ? 'Sending…' : 'Resend')}</button>}
    </div>
  )
}

/** Account & security on my own profile: email, password, sessions. */
export function AccountSecurity({ me }) {
  const { t } = useLang()
  const spring = useSpring()
  const [open, setOpen] = useState(null) // null | 'email' | 'password'
  const [notice, setNotice] = useState(null)
  if (!me) return null
  const done = (msg) => { setOpen(null); setNotice(msg) }
  return (
    <section className="acct">
      <div className="blk-title">{t('Account & security')}</div>
      <div className="acct-row">
        <span><small>{t('Email')}</small><b>{me.email}</b></span>
        <span className={`acct-tag ${me.email_verified ? 'ok' : 'warn'}`}>{me.email_verified ? <><Check size={13} /> {t('Confirmed')}</> : t('Not confirmed')}</span>
        <button className="btn text small" onClick={() => setOpen(open === 'email' ? null : 'email')}>{t('Change')}</button>
      </div>
      <AnimatePresence initial={false}>
        {open === 'email' && <motion.div key="e" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={spring} style={{ overflow: 'hidden' }}>
          <EmailForm onDone={(email) => done(t('We sent a confirmation link to {email}.', { email }))} onCancel={() => setOpen(null)} />
        </motion.div>}
      </AnimatePresence>
      <div className="acct-row">
        <span><small>{t('Password')}</small><b>••••••••</b></span>
        <button className="btn text small" onClick={() => setOpen(open === 'password' ? null : 'password')}>{t('Change')}</button>
      </div>
      <AnimatePresence initial={false}>
        {open === 'password' && <motion.div key="p" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={spring} style={{ overflow: 'hidden' }}>
          <PasswordForm onDone={() => done(t('Password changed. Other devices were logged out.'))} onCancel={() => setOpen(null)} />
        </motion.div>}
      </AnimatePresence>
      {notice && <div className="acct-notice" role="status">{notice}</div>}
      <div className="acct-actions">
        <button className="btn small" onClick={() => logoutEverywhere().then(() => setNotice(t('Logged out on every other device.'))).catch((e) => setNotice(t(e.message)))}>{t('Log out everywhere')}</button>
        <button className="btn small" onClick={logout}>{t('Log out')}</button>
      </div>
    </section>
  )
}

function useForm(submit) {
  const { t } = useLang()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await submit() } catch (err) { setError(err.status ? t(err.message) : t('Could not reach the server. Try again in a moment.')) } finally { setBusy(false) }
  }
  return { busy, error, run }
}

function EmailForm({ onDone, onCancel }) {
  const { t } = useLang()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const f = useForm(async () => { await changeEmail(email.trim(), password); onDone(email.trim()) })
  return (
    <form className="acct-form" onSubmit={f.run}>
      <input className="ce-input" type="email" placeholder={t('New email')} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus />
      <input className="ce-input" type="password" placeholder={t('Current password')} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
      {f.error && <div className="ce-error" role="alert">{f.error}</div>}
      <div className="acct-form-actions">
        <button type="button" className="btn text small" onClick={onCancel}>{t('Cancel')}</button>
        <button type="submit" className="btn small primary" disabled={f.busy || !email.includes('@') || !password}>{t(f.busy ? 'Saving…' : 'Save')}</button>
      </div>
    </form>
  )
}

function PasswordForm({ onDone, onCancel }) {
  const { t } = useLang()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const f = useForm(async () => { await changePassword(current, next); onDone() })
  return (
    <form className="acct-form" onSubmit={f.run}>
      <input className="ce-input" type="password" placeholder={t('Current password')} value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" autoFocus />
      <input className="ce-input" type="password" placeholder={t('New password')} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" maxLength={128} />
      <small className="login-note">{t('At least 8 characters')}</small>
      {f.error && <div className="ce-error" role="alert">{f.error}</div>}
      <div className="acct-form-actions">
        <button type="button" className="btn text small" onClick={onCancel}>{t('Cancel')}</button>
        <button type="submit" className="btn small primary" disabled={f.busy || !current || next.length < 8}>{t(f.busy ? 'Saving…' : 'Save')}</button>
      </div>
    </form>
  )
}

/**
 * Links from our mails open the site with ?verify=<token> or ?reset=<token>. This reads them once,
 * clears them from the address bar, and shows the result (or the new-password form) in a small card.
 */
export function AuthLinks() {
  const { t } = useLang()
  const spring = useSpring()
  const [link] = useState(() => {
    const q = new URLSearchParams(location.search)
    return q.get('verify') ? { kind: 'verify', token: q.get('verify') } : q.get('reset') ? { kind: 'reset', token: q.get('reset') } : null
  })
  const [state, setState] = useState(link ? (link.kind === 'verify' ? 'verifying' : 'reset') : null)
  const [error, setError] = useState(null)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!link) return
    const q = new URLSearchParams(location.search)
    q.delete('verify'); q.delete('reset')
    history.replaceState(history.state, '', `${location.pathname}${q.size ? `?${q}` : ''}${location.hash}`)
    if (link.kind === 'verify') verifyEmail(link.token).then(() => setState('verified')).catch((e) => { setError(t(e.message)); setState('failed') })
  }, [link]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!state) return null
  const close = () => setState(null)
  const reset = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await resetPassword(link.token, password); setState('reset-done') } catch (err) { setError(t(err.message)) } finally { setBusy(false) }
  }
  return (
    <div className="auth-link-scrim" onPointerDown={(e) => e.target === e.currentTarget && state !== 'verifying' && close()}>
      <motion.div className="auth-link surface" role="dialog" aria-modal="true" initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={spring}>
        {state !== 'verifying' && <button className="btn icon small ghost auth-link-x" onClick={close} aria-label={t('Close')}><X size={18} /></button>}
        {state === 'verifying' && <p>{t('Confirming your email…')}</p>}
        {state === 'verified' && <>
          <div className="auth-link-ic ok"><Check size={26} /></div>
          <h3>{t('Email confirmed')}</h3>
          <p>{t('You can now add friends, create events and join event chats.')}</p>
          <button className="btn primary" onClick={close}>{t('Start exploring')}</button>
        </>}
        {state === 'failed' && <>
          <div className="auth-link-ic bad"><X size={26} /></div>
          <h3>{t('That link didn’t work')}</h3>
          <p>{error} {t('Log in and use Resend on your profile to get a fresh one.')}</p>
          <button className="btn" onClick={close}>{t('Close')}</button>
        </>}
        {state === 'reset' && <form onSubmit={reset}>
          <h3>{t('Choose a new password')}</h3>
          <p>{t('This logs you out on every other device.')}</p>
          <input className="ce-input" type="password" placeholder={t('New password')} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" maxLength={128} autoFocus />
          <small className="login-note">{t('At least 8 characters')}</small>
          {error && <div className="ce-error" role="alert">{error}</div>}
          <button type="submit" className="btn primary" disabled={busy || password.length < 8}>{t(busy ? 'Saving…' : 'Save new password')}</button>
        </form>}
        {state === 'reset-done' && <>
          <div className="auth-link-ic ok"><Check size={26} /></div>
          <h3>{t('Password changed')}</h3>
          <p>{t('You’re logged in on this device.')}</p>
          <button className="btn primary" onClick={close}>{t('Continue')}</button>
        </>}
      </motion.div>
    </div>
  )
}
