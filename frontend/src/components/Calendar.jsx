import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { DayPicker } from 'react-day-picker'
import { enGB, pl } from 'react-day-picker/locale'
import 'react-day-picker/style.css'
import { useSpring } from '../config/store'
import { locale, useLang } from '../i18n'
import { Calendar as CalendarIcon } from './Icons'

const pad = (n) => String(n).padStart(2, '0')
export const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const fromYmd = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
export const startOfToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d }

/** "sob., 18 paź" / "Sat 18 Oct": short day label in the UI language. */
export const fmtDay = (d) => d.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })

/**
 * The app's calendar (react-day-picker, restyled in global.css under .syr-cal): Monday first,
 * Polish or English, past days off by default. Pass mode="single" or mode="range" like DayPicker.
 */
export function Calendar({ allowPast = false, ...props }) {
  const { lang } = useLang()
  return (
    <DayPicker
      className="syr-cal"
      locale={lang === 'pl' ? pl : enGB}
      weekStartsOn={1}
      showOutsideDays
      disabled={allowPast ? undefined : { before: startOfToday() }}
      {...props}
    />
  )
}

/** Click-away / Escape closing for a small popover. */
export function usePopover() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])
  return { open, setOpen, ref }
}

/** A date input that opens the calendar in a popover. `value` / onChange use "YYYY-MM-DD". */
export function DateField({ value, onChange, label }) {
  const spring = useSpring()
  const { open, setOpen, ref } = usePopover()
  const date = value ? fromYmd(value) : null
  return (
    <div className="date-field" ref={ref}>
      <button type="button" className={`ce-input date-btn ${open ? 'open' : ''}`} onClick={() => setOpen(!open)} aria-label={label} aria-expanded={open}>
        <CalendarIcon size={16} />{date ? fmtDay(date) : '—'}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="cal-pop surface" initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.97 }} transition={spring}>
            <Calendar mode="single" selected={date} defaultMonth={date || undefined} required onSelect={(d) => { if (d) { onChange(ymd(d)); setOpen(false) } }} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
