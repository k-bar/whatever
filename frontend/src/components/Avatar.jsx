import { assetUrl } from '../data/api'

/**
 * A person's (or chat's) round picture, the same everywhere: their photo, else their initial on a colour
 * picked from their id, so one person keeps one colour on the profile, in chats, join requests and boxes.
 */
export const AVATAR_COLORS = ['#e7392b', '#2b6be7', '#0fa37f', '#f2a900', '#7c4dff']
export const avatarColor = (id) => AVATAR_COLORS[Math.abs(Number(id) || 0) % AVATAR_COLORS.length]

/** user: { id, display_name, photos }. `label` replaces the name for the initial (e.g. a chat's title). */
export function Avatar({ user, size = 44, photo = user?.photos?.[0], label, className = '' }) {
  const letter = (label || user?.display_name || '?')[0].toUpperCase()
  return (
    <span className={`pp-av ${className}`} style={{ width: size, height: size, fontSize: size * 0.42, background: photo ? `center / cover url(${assetUrl(photo)})` : avatarColor(user?.id) }}>
      {!photo && letter}
    </span>
  )
}
