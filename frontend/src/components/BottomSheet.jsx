import { useEffect, useRef, useState } from 'react'
import { motion, useAnimation } from 'framer-motion'
import { useSpring } from '../config/store'

/**
 * Mobile sheet: snaps to half the screen (map on top, content below) or full screen.
 * Drag the grip (or the header area) to move between half / full / closed.
 */
export function BottomSheet({ open, onClose, children, initial = 'half' }) {
  const spring = useSpring()
  const controls = useAnimation()
  const [snap, setSnap] = useState(initial)
  const vh = useRef(window.innerHeight)

  const Y = { full: 0, half: () => vh.current * 0.5, closed: () => vh.current }
  const yFor = (s) => (typeof Y[s] === 'function' ? Y[s]() : Y[s])

  useEffect(() => {
    vh.current = window.innerHeight
    if (open) { setSnap(initial); controls.start({ y: yFor(initial) }) }
    else controls.start({ y: yFor('closed') })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial])

  const onDragEnd = (_, info) => {
    const y = info.point.y
    const v = info.velocity.y
    let next
    if (v > 600) next = snap === 'full' ? 'half' : 'closed'
    else if (v < -600) next = 'full'
    else next = y < vh.current * 0.28 ? 'full' : y < vh.current * 0.78 ? 'half' : 'closed'
    if (next === 'closed') { onClose(); return }
    setSnap(next)
    controls.start({ y: yFor(next) })
  }

  return (
    <motion.div className="sheet surface" animate={controls} initial={{ y: vh.current }} transition={spring}
      drag="y" dragConstraints={{ top: 0, bottom: vh.current }} dragElastic={0.12} onDragEnd={onDragEnd}
      style={{ pointerEvents: open ? 'auto' : 'none' }}>
      <div className="grip" />
      <div className="sheet-body" onPointerDownCapture={(e) => { if (snap === 'full') e.stopPropagation() }}>{children}</div>
    </motion.div>
  )
}
