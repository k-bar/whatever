import { Suspense, lazy } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSpring } from '../config/store'
import { locale, useLang } from '../i18n'
import { Calendar as CalendarIcon } from './Icons'

const pad = (n) => String(n).padStart(2, '0')
export const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const fromYmd = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
export const startOfToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d }

/** "sob., 18 paź" / "Sat 18 Oct": short day label in the UI language. */
export const fmtDay = (d) => { const s = d.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' }); return s[0].toUpperCase() + s.slice(1) }

/**
 * The app's calendar (react-day-picker, restyled in global.css under .syr-cal): Monday first,
 * Polish or English, past days off by default. Pass mode="single" or mode="range" like DayPicker.
 */
// react-day-picker (~60 kB with its locales and stylesheet) is only needed once someone opens a date
// picker, so it loads on demand instead of sitting in the first bundle.
// the two locales come straight from date-fns: 'react-day-picker/locale' would drag in all ~100 of them (690 kB)
const DayPickerLazy = lazy(() => Promise.all([import('react-day-picker'), import('date-fns/locale/pl'), import('date-fns/locale/en-GB'), import('react-day-picker/style.css')])
  .then(([m, pl, en]) => ({ default: ({ lang, ...props }) => <m.DayPicker locale={lang === 'pl' ? pl.pl : en.enGB} {...props} /> })))

export function Calendar({ allowPast = false, ...props }) {
  const { lang } = useLang()
  return (
    <Suspense fallback={<div className="syr-cal syr-cal-loading" aria-busy="true" />}>
      <DayPickerLazy
        lang={lang}
        className="syr-cal"
        weekStartsOn={1}
        showOutsideDays
        disabled={allowPast ? undefined : { before: startOfToday() }}
        {...props}
      />
    </Suspense>
  )
}

// usePopover lives in hooks/usePopover.js; re-exported for the existing imports
export { usePopover } from '../hooks/usePopover'
import { usePopover } from '../hooks/usePopover'

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
