import { useEffect, useRef } from 'react'

/**
 * For a scrolling list: sets `fade-top` / `fade-bottom` on the element while there is more to scroll in
 * that direction (CSS draws soft edges, see .scroll-fade in global.css), and `scrolling` for a moment
 * after each scroll so the scrollbar can show up and then hide again.
 * Returns a callback ref (the list may mount long after its parent); `ref.current` is the element.
 */
export function useScrollFade() {
  const api = useRef(null)
  if (!api.current) {
    let detach = null
    const ref = (el) => {
      detach?.(); detach = null
      ref.current = el
      if (!el) return
      let hide
      const update = () => {
        el.classList.toggle('fade-top', el.scrollTop > 2)
        el.classList.toggle('fade-bottom', el.scrollTop + el.clientHeight < el.scrollHeight - 2)
      }
      const onScroll = () => {
        update()
        el.classList.add('scrolling')
        clearTimeout(hide)
        hide = setTimeout(() => el.classList.remove('scrolling'), 900)
      }
      update()
      el.addEventListener('scroll', onScroll, { passive: true })
      const ro = new ResizeObserver(update) // the list grows / shrinks as boxes open, close and expand
      ro.observe(el)
      const mo = new MutationObserver(update)
      mo.observe(el, { childList: true, subtree: true })
      detach = () => { clearTimeout(hide); el.removeEventListener('scroll', onScroll); ro.disconnect(); mo.disconnect() }
    }
    ref.current = null
    api.current = ref
  }
  useEffect(() => () => api.current(null), [])
  return api.current
}
