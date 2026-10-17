import { useState } from 'react'
import { login, register } from '../data/api'
import { useLang } from '../i18n'

/**
 * Log in / sign up (POST /auth/login, /auth/register). On success the token is stored and
 * onDone() runs; everything listening to onAuthChange() updates too. `compact`: placeholders instead of
 * labels (the small card under the top-right "Log in" button).
 */
export function LoginForm({ onDone, intro, compact = false }) {
  const { t } = useLang()
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const signup = mode === 'register'
  const valid = email.includes('@') && password.length >= (signup ? 8 : 1) && (!signup || name.trim())

  const submit = async (e) => {
    e.preventDefault()
    if (!valid || busy) return
    setBusy(true); setError(null)
    try {
      if (signup) await register(name.trim(), email.trim(), password)
      else await login(email.trim(), password)
      onDone?.()
    } catch (err) {
      setError(err.status ? t(err.message) : t('Could not reach the server. Try again in a moment.'))
      setBusy(false)
    }
  }

  return (
    <form className={`login-form ${compact ? 'compact' : ''}`} onSubmit={submit}>
      {intro && <p className="login-intro">{intro}</p>}
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
      <label className="ce-field">
        {!compact && <span className="ce-label">{t('Password')}</span>}
        <input className="ce-input" placeholder={compact ? t('Password') : undefined} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={signup ? 'new-password' : 'current-password'} />
        {signup && <small className="login-note">{t('At least 8 characters')}</small>}
      </label>
      {error && <div className="ce-error" role="alert">{error}</div>}
      <button type="submit" className="btn primary ce-done" disabled={!valid || busy}>
        {busy ? t('One moment…') : t(signup ? 'Create account' : 'Log in')}
      </button>
      <button type="button" className="btn text login-switch" onClick={() => { setMode(signup ? 'login' : 'register'); setError(null) }}>
        {t(signup ? 'Already have an account? Log in' : 'New here? Create an account')}
      </button>
    </form>
  )
}
