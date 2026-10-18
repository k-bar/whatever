/**
 * Tiny request cache: the same key within `ttl` ms returns the stored promise, so a panel that
 * mounts twice (or three components that all want /me) costs one request. In-flight calls are
 * shared too. Failures are not kept, so the next caller retries.
 */
const store = new Map()

export function cached(key, ttl, fn) {
  const hit = store.get(key)
  const now = Date.now()
  if (hit && hit.until > now) return hit.promise
  const promise = Promise.resolve().then(fn)
  store.set(key, { promise, until: now + ttl })
  promise.catch(() => { if (store.get(key)?.promise === promise) store.delete(key) })
  return promise
}

/** Drop entries whose key starts with `prefix` (or everything). Call after a write that changes them. */
export function invalidate(prefix = '') {
  for (const k of [...store.keys()]) if (k.startsWith(prefix)) store.delete(k)
}

export const MIN = 60 * 1000
