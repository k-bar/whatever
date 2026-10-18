import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useChat } from '../data/chat'
import { assetUrl } from '../data/api'
import { fmtWhen } from '../mapboxes/curate'
import { locale, useLang } from '../i18n'
import { needsVerify, useMe, VerifyBanner } from './Account'
import { ChevronL, X } from './Icons'
import { LoginForm } from './LoginForm'
import { Avatar } from './Avatar'

const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString()
const GROUP_MS = 5 * 60 * 1000 // consecutive messages from one person within 5 min share a header

/**
 * One event's chat: history (older pages on demand), live messages over the shared socket, a composer.
 * Logged out: the login form. Not confirmed yet: read-only with the "confirm your email" banner.
 */
export function EventChat({ target, onBack, onOpenEvent, onOpenUser }) {
  const { t } = useLang()
  const me = useMe()
  const chat = useChat(me ? target : null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const scroller = useRef(null)
  const stick = useRef(true) // follow new messages unless the user scrolled up to read
  const lastId = chat.messages.at(-1)?.id

  // keep the view pinned to the newest message; keep the position when an older page is prepended
  const prevHeight = useRef(0)
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    if (stick.current) el.scrollTop = el.scrollHeight
    else if (prevHeight.current && el.scrollHeight > prevHeight.current && el.scrollTop < 40) el.scrollTop += el.scrollHeight - prevHeight.current
    prevHeight.current = el.scrollHeight
  }, [chat.messages])

  // seen: everything up to the newest message (only matters for members, the server ignores the rest)
  useEffect(() => {
    if (lastId && chat.info?.joined && lastId > (chat.info.last_read_id || 0) && document.visibilityState === 'visible') chat.read(lastId)
  }, [lastId, chat.info?.joined]) // eslint-disable-line react-hooks/exhaustive-deps

  const send = async () => {
    const body = draft.trim()
    if (!body || sending) return
    setSending(true); setError(null); stick.current = true
    try { await chat.send(body); setDraft('') } catch (e) { setError(t(e.message)) } finally { setSending(false) }
  }

  if (me === null) {
    return (
      <div className="chat">
        {onBack && <button className="btn text small chat-back" onClick={onBack}><ChevronL size={16} /> {t('All chats')}</button>}
        <div className="pp-loggedout"><p>{t('Log in to talk with people going to this event.')}</p><LoginForm /></div>
      </div>
    )
  }

  const info = chat.info
  const canWrite = !!me && !needsVerify(me)
  const isHost = info && me && info.host_user_id === me.id
  return (
    <div className="chat">
      <header className="chat-head">
        {onBack && <button className="btn icon small ghost" onClick={onBack} aria-label={t('All chats')}><ChevronL size={18} /></button>}
        <button className="chat-title" onClick={() => onOpenEvent?.(info)} disabled={!onOpenEvent || !info}>
          {info?.image_url && <span className="chat-thumb" style={{ backgroundImage: `url(${assetUrl(info.image_url)})` }} />}
          <span><b>{info?.title || t('Loading…')}</b>{info?.starts_at && <small>{fmtWhen(info.starts_at)}</small>}</span>
        </button>
        {info && canWrite && (
          <button className={`btn small ${info.joined ? '' : 'primary'}`} onClick={() => chat.follow(!info.joined).catch((e) => setError(t(e.message)))}
            title={t(info.joined ? 'Stop showing this chat in Messages' : 'Show this chat in Messages and count new messages')}>
            {t(info.joined ? 'Following' : 'Follow')}
          </button>
        )}
      </header>

      <div className="chat-scroll" ref={scroller} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60 }}>
        {chat.error && <div className="res-empty">{t(chat.error.message)}</div>}
        {chat.hasOlder && <button className="btn text small chat-older" onClick={() => { stick.current = false; chat.older() }}>{t('Earlier messages')}</button>}
        {info && !chat.messages.length && <div className="chat-empty">{t('No messages yet. Ask who’s going, share a plan, or say hi.')}</div>}
        {chat.messages.map((m, i) => {
          const prev = chat.messages[i - 1]
          const newDay = !prev || !sameDay(prev.created_at, m.created_at)
          const head = newDay || prev.user.id !== m.user.id || new Date(m.created_at) - new Date(prev.created_at) > GROUP_MS
          const mine = me && m.user.id === me.id
          return (
            <div key={m.id}>
              {newDay && <div className="chat-day">{new Date(m.created_at).toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' })}</div>}
              <div className={`chat-msg ${mine ? 'mine' : ''} ${head ? 'head' : ''} ${m.deleted ? 'deleted' : ''}`}>
                {head && !mine
                  ? <button className="chat-av" onClick={() => onOpenUser?.(m.user.id)} aria-label={m.user.display_name}><Avatar user={{ id: m.user.id, display_name: m.user.display_name, photos: m.user.photo ? [m.user.photo] : [] }} size={30} /></button>
                  : <span className="chat-av" />}
                <div className="chat-bubble-wrap">
                  {head && <div className="chat-meta">{!mine && <b>{m.user.display_name}</b>}<time>{new Date(m.created_at).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })}</time></div>}
                  <div className="chat-bubble">{m.deleted ? <i>{t('Message deleted')}</i> : m.body}</div>
                </div>
                {!m.deleted && (mine || isHost) && (
                  <button className="chat-del" onClick={() => chat.remove(m.id).catch((e) => setError(t(e.message)))} aria-label={t('Delete message')} title={t('Delete message')}><X size={13} /></button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {error && <div className="ce-error chat-error" role="alert">{error}</div>}
      {me && !canWrite
        ? <VerifyBanner me={me} compact />
        : (
          <form className="chat-compose" onSubmit={(e) => { e.preventDefault(); send() }}>
            <textarea rows={1} value={draft} maxLength={2000} placeholder={t('Write a message…')} disabled={!info}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} />
            <button type="submit" className="btn small primary" disabled={!draft.trim() || sending}>{t('Send')}</button>
          </form>
        )}
    </div>
  )
}
