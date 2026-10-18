/**
 * Opening hours as the API sends them for places: { monday: '12:00-23:00', ..., sunday: '10:00-22:00' }
 * (OpenStreetMap's opening_hours turned into one range per day; a missing day = closed or unknown).
 * Times are Warsaw time, whatever the phone's own time zone is.
 */

export const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const LABELS = { monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed', thursday: 'Thu', friday: 'Fri', saturday: 'Sat', sunday: 'Sun' }
export const dayLabel = (day) => LABELS[day]

const WARSAW = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', weekday: 'long', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** Warsaw's day ('monday'…) and minutes since midnight right now. */
export function warsawNow(at = new Date()) {
  const parts = Object.fromEntries(WARSAW.formatToParts(at).map((p) => [p.type, p.value]))
  return { day: parts.weekday.toLowerCase(), minutes: Number(parts.hour) * 60 + Number(parts.minute) }
}

/** '19:00-04:00' -> [1140, 240]; anything else -> null. */
function range(s) {
  const m = /^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$/.exec(String(s || '').trim())
  return m ? [Number(m[1]) * 60 + Number(m[2]), Number(m[3]) * 60 + Number(m[4])] : null
}

export const hasWeekHours = (hours) => Boolean(hours && typeof hours === 'object' && DAYS.some((d) => range(hours[d])))

/**
 * Open right now? true / false, or null when the place has no usable hours.
 * A range past midnight (a bar open 18:00-02:00) counts on the night it starts and the early hours after.
 */
export function isOpenNow(hours, at = new Date()) {
  if (!hasWeekHours(hours)) return null
  const { day, minutes } = warsawNow(at)
  const today = range(hours[day])
  const yesterday = range(hours[DAYS[(DAYS.indexOf(day) + 6) % 7]])
  if (today) {
    const [start, end] = today
    if (end > start ? minutes >= start && minutes < end : minutes >= start) return true
  }
  if (yesterday) {
    const [start, end] = yesterday
    if (end <= start && minutes < end) return true // still open from last night
  }
  return false
}

/** For the map box: open now?, today's hours, and the whole week in order (today first). */
export function weekHours(hours, at = new Date()) {
  if (!hasWeekHours(hours)) return null
  const { day } = warsawNow(at)
  const i = DAYS.indexOf(day)
  const week = [...DAYS.slice(i), ...DAYS.slice(0, i)].map((d) => ({ day: d, hours: range(hours[d]) ? hours[d].replace('-', '–') : null }))
  return { open: isOpenNow(hours, at), today: week[0].hours, week }
}
