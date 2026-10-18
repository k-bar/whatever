import { useEffect, useRef, useState } from 'react'

/**
 * A small popover (date picker, pin box, language, weather…): open state, plus closing on a tap outside
 * `ref` and on Escape. Escape is marked handled (preventDefault) so App's own Escape (close the create
 * panel / slide-over / newest box) leaves whatever is behind the popover alone.
 */
export function usePopover(initial = false) {
  const [open, setOpen] = useState(initial)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); setOpen(false) } }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])
  return { open, setOpen, ref }
}
