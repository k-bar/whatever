/**
 * Event chats (backend/app/routers/chats.py, app/realtime.py). History and sending go over REST;
 * new messages arrive over one shared WebSocket (GET /ws) while the user is logged in. The socket
 * reconnects with backoff and, on reconnect, each open chat catches up with ?after=<last id>.
 *
 * A chat is addressed by its event: kind 'event' (any map pin with a numeric id) or 'userevent'
 * (friends-only / invite-only events, whose pins carry user_event_id and a negative id).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { apiBase, authedCall, onAuthChange, sessionToken } from './api'

export const chatTarget = (feature) => {
  const p = feature?.properties || {}
  if (typeof p.event_id === 'number') return { kind: 'event', id: p.event_id }
  if (p.user_event_id) return { kind: 'userevent', id: p.user_event_id }
  return null
}
const path = ({ kind, id }) => `/chats/${kind}/${id}`

export const fetchChat = (t) => authedCall(path(t))
export const fetchMessages = (t, q = {}) => authedCall(`${path(t)}/messages?${new URLSearchParams({ limit: 50, ...q })}`)
export const postMessage = (t, body) => authedCall(`${path(t)}/messages`, { method: 'POST', body: { body } })
export const deleteMessage = (id) => authedCall(`/chats/messages/${id}`, { method: 'DELETE' })
export const markRead = (t, lastReadId) => authedCall(`${path(t)}/read`, { method: 'PUT', body: { last_read_id: lastReadId } })
export const followChat = (t) => authedCall(`${path(t)}/membership`, { method: 'PUT' })
export const leaveChat = (t) => authedCall(`${path(t)}/membership`, { method: 'DELETE' })
export const fetchMyChats = () => authedCall('/me/chats')

/* ---------- the shared socket ---------- */

function socketUrl() {
  const base = apiBase.startsWith('http') ? apiBase : `${location.origin}${apiBase}`
  return `${base.replace(/^http/, 'ws')}/ws`
}

const listeners = new Set() // every frame, for unread badges and open chats
const keys = new Map() // chat key -> number of open views subscribed to it
let ws = null, ready = false, retry = 0, timer = null, ping = null, wanted = false

function send(frame) { if (ws && ready) ws.send(JSON.stringify(frame)) }

function connect() {
  clearTimeout(timer)
  const token = sessionToken()
  if (!wanted || !token || ws) return
  const sock = new WebSocket(socketUrl())
  ws = sock
  sock.onopen = () => sock.send(JSON.stringify({ type: 'auth', token }))
  sock.onmessage = (e) => {
    let frame
    try { frame = JSON.parse(e.data) } catch { return }
    if (frame.type === 'ready') {
      ready = true; retry = 0
      for (const key of keys.keys()) send({ type: 'subscribe', key })
      ping = setInterval(() => send({ type: 'ping' }), 25000) // CloudFront closes idle sockets
    }
    listeners.forEach((fn) => fn(frame))
  }
  sock.onclose = (e) => {
    if (ws === sock) { ws = null; ready = false; clearInterval(ping) }
    listeners.forEach((fn) => fn({ type: 'closed' }))
    if (e.code === 4401) return // bad / ended session: wait for the next login
    if (wanted) timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** retry++))
  }
}

function disconnect() {
  clearTimeout(timer); clearInterval(ping)
  const sock = ws
  ws = null; ready = false
  sock?.close()
}

/** Keep the socket up while someone is logged in (called once, from App). */
export function startChatSocket() {
  wanted = true
  const sync = () => { disconnect(); if (sessionToken()) connect() }
  sync()
  const off = onAuthChange(sync)
  return () => { off(); wanted = false; disconnect() }
}

export function onChatFrame(fn) { listeners.add(fn); return () => listeners.delete(fn) }

function subscribe(key) {
  keys.set(key, (keys.get(key) || 0) + 1)
  if (keys.get(key) === 1) send({ type: 'subscribe', key })
  return () => {
    const n = keys.get(key) - 1
    if (n > 0) { keys.set(key, n); return }
    keys.delete(key); send({ type: 'unsubscribe', key })
  }
}

/* ---------- hooks ---------- */

/** One chat: info, messages (oldest first), live updates, older pages and sending. */
export function useChat(target) {
  const [info, setInfo] = useState(null)
  const [messages, setMessages] = useState([])
  const [error, setError] = useState(null)
  const [hasOlder, setHasOlder] = useState(false)
  const last = useRef(0)
  const k = target ? `${target.kind}:${target.id}` : null

  const add = useCallback((list) => {
    if (!list.length) return
    setMessages((cur) => {
      const byId = new Map(cur.map((m) => [m.id, m]))
      list.forEach((m) => byId.set(m.id, m))
      return [...byId.values()].sort((a, b) => a.id - b.id)
    })
    last.current = Math.max(last.current, ...list.map((m) => m.id))
  }, [])

  useEffect(() => {
    if (!target) return
    let alive = true
    setInfo(null); setMessages([]); setError(null); last.current = 0
    Promise.all([fetchChat(target), fetchMessages(target)])
      .then(([i, msgs]) => { if (!alive) return; setInfo(i); add(msgs); setHasOlder(msgs.length >= 50) })
      .catch((e) => alive && setError(e))
    return () => { alive = false }
  }, [k]) // eslint-disable-line react-hooks/exhaustive-deps

  // the server answers with the canonical key (a published user event is "event:<id>")
  const liveKey = info?.key
  useEffect(() => {
    if (!liveKey) return
    const unsub = subscribe(liveKey)
    const off = onChatFrame((f) => {
      if (f.type === 'message' && f.key === liveKey) add([f.message])
      else if (f.type === 'deleted' && f.key === liveKey) setMessages((cur) => cur.map((m) => (m.id === f.id ? { ...m, body: null, deleted: true } : m)))
      else if (f.type === 'subscribed' && f.key === liveKey && last.current) {
        fetchMessages({ kind: info.kind, id: info.target_id }, { after: last.current, limit: 200 }).then(add).catch(() => {}) // missed while offline
      }
    })
    return () => { off(); unsub() }
  }, [liveKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const t = info ? { kind: info.kind, id: info.target_id } : target
  return {
    info, messages, error, hasOlder,
    send: async (body) => { const m = await postMessage(t, body); add([m]); setInfo((i) => i && { ...i, joined: true }); return m },
    remove: (id) => deleteMessage(id),
    older: async () => {
      if (!messages.length) return
      const page = await fetchMessages(t, { before: messages[0].id })
      setHasOlder(page.length >= 50); add(page)
    },
    read: (id) => markRead(t, id).then(setInfo).catch(() => {}),
    follow: async (on) => setInfo(on ? await followChat(t) : (await leaveChat(t), { ...info, joined: false, unread: 0 })),
  }
}

/** Messages list (GET /me/chats), kept fresh by the socket. total = unread across chats, for the badge. */
export function useMyChats(enabled = true) {
  const [chats, setChats] = useState(null)
  const reload = useCallback(() => {
    if (!sessionToken()) { setChats([]); return }
    fetchMyChats().then(setChats).catch(() => setChats([]))
  }, [])
  useEffect(() => {
    if (!enabled) return
    reload()
    const offAuth = onAuthChange(reload)
    let pending = null
    const off = onChatFrame((f) => {
      if (f.type !== 'message' && f.type !== 'deleted') return
      clearTimeout(pending); pending = setTimeout(reload, 400) // a burst of messages = one reload
    })
    return () => { off(); offAuth(); clearTimeout(pending) }
  }, [enabled, reload])
  const total = (chats || []).reduce((n, c) => n + c.unread, 0)
  return { chats, total, reload }
}
