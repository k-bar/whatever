import { useState } from 'react'
import { fetchMe, forgotPassword, login, register } from '../data/api'
import { useLang } from '../i18n'

/**
 * Log in / sign up / forgot password (POST /auth/login, /auth/register, /auth/password/forgot).
 * Signing up logs you in straight away and mails a confirmation link. When the server requires a
 * confirmed email (me.verify_required) the form then says so and onDone() runs when you close that
 * note; otherwise onDone() runs straight away. Everything listening to onAuthChange() updates too.
 * `compact`: placeholders instead of labels (the small card under the top-right "Log in" button).
 */
export function LoginForm({ onDone, onRegistered, intro, compact = false }) {
  const { t } = useLang()
  const [mode, setMode] = useState('login') // 'login' | 'register' | 'forgot' | 'sent' | 'reset-sent'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const signup = mode === 'register'
  const forgot = mode === 'forgot'
  const valid = email.includes('@') && (forgot || password.length >= (signup ? 8 : 1)) && (!signup || name.trim())
  const go = (m) => { setMode(m); setError(null) }

  const submit = async (e) => {
    e.preventDefault()
    if (!valid || busy) return
    setBusy(true); setError(null)
    try {
      if (signup) {
        await register(name.trim(), email.trim(), password)
        if ((await fetchMe())?.verify_required === false) onDone?.()
        else { onRegistered?.(); setMode('sent') }
      }
      else if (forgot) { await forgotPassword(email.trim()); setMode('reset-sent') }
      else { await login(email.trim(), password); onDone?.() }
    } catch (err) {
      setError(err.status ? t(err.message) : t('Could not reach the server. Try again in a moment.'))
    } finally {
      setBusy(false)
    }
  }

  if (mode === 'sent' || mode === 'reset-sent') {
    return (
      <div className={`login-form login-sent ${compact ? 'compact' : ''}`}>
        <div className="login-mail" aria-hidden>✉</div>
        <p><b>{t('Check your inbox')}</b></p>
        <p>{mode === 'sent'
          ? t('We sent a link to {email}. Open it to confirm your address: then you can add friends, create events and join event chats.', { email: email.trim() })
          : t('If {email} has an account, a link to choose a new password is on its way. It works for one hour.', { email: email.trim() })}</p>
        <button type="button" className="btn primary ce-done" onClick={() => (mode === 'sent' ? onDone?.() : go('login'))}>
          {t(mode === 'sent' ? 'Got it' : 'Back to log in')}
        </button>
      </div>
    )
  }

  return (
    <form className={`login-form ${compact ? 'compact' : ''}`} onSubmit={submit}>
      {intro && <p className="login-intro">{intro}</p>}
      {forgot && <p className="login-intro">{t('Enter your email and we will send you a link to choose a new password.')}</p>}
      {signup && (
        <label className="ce-field">
          {!compact && <span className="ce-label">{t('Your name')}</span>}
          <input className="ce-input" placeholder={compact ? t('Your name') : undefined} value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoComplete="name" autoFocus />
        </label>
      )}
      <label className="ce-field">
        {!compact && <span className="ce-label">{t('Email')}</span>}
        <input className="ce-input" placeholder={compact ? t('Email') : undefined} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus={!signup} />
      </label>
      {!forgot && (
        <label className="ce-field">
          {!compact && <span className="ce-label">{t('Password')}</span>}
          <input className="ce-input" placeholder={compact ? t('Password') : undefined} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={signup ? 'new-password' : 'current-password'} maxLength={128} />
          {signup && <small className="login-note">{t('At least 8 characters')}</small>}
          {mode === 'login' && <button type="button" className="btn text login-forgot" onClick={() => go('forgot')}>{t('Forgot password?')}</button>}
        </label>
      )}
      {error && <div className="ce-error" role="alert">{error}</div>}
      <button type="submit" className="btn primary ce-done" disabled={!valid || busy}>
        {busy ? t('One moment…') : t(signup ? 'Create account' : forgot ? 'Send reset link' : 'Log in')}
      </button>
      <button type="button" className="btn text login-switch" onClick={() => go(signup || forgot ? 'login' : 'register')}>
        {t(signup ? 'Already have an account? Log in' : forgot ? 'Back to log in' : 'New here? Create an account')}
      </button>
    </form>
  )
}
