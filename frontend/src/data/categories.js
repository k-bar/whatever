import { translate } from '../i18n'

// Mirrors backend/app/categories.py. Colours are the only frontend addition.
export const CATEGORIES = {
  music: { label: 'Music', color: '#e7392b' },
  nightlife: { label: 'Nightlife', color: '#8b5cf6' },
  theatre: { label: 'Theatre', color: '#d946ef' },
  film: { label: 'Film', color: '#f59e0b' },
  exhibitions: { label: 'Exhibitions', color: '#0ea5e9' },
  meetups: { label: 'Meetups', color: '#10b981' },
  grzybki: { label: 'Grzybki', color: '#a16207' },
  study_buddies: { label: 'Study buddies', color: '#6366f1' },
  running: { label: 'Running', color: '#f97316' },
  yoga: { label: 'Yoga', color: '#14b8a6' },
  sports: { label: 'Sports', color: '#22c55e' },
  festivals: { label: 'Festivals', color: '#ec4899' },
  markets: { label: 'Markets', color: '#eab308' },
  culture: { label: 'Culture', color: '#3b82f6' },
  education: { label: 'Education', color: '#64748b' },
  family: { label: 'Family & kids', color: '#fb7185' },
  business: { label: 'Business', color: '#475569' },
  health: { label: 'Health', color: '#06b6d4' },
  other: { label: 'Other', color: '#9ca3af' },
}

export const categoryColor = (slug) => CATEGORIES[slug]?.color || CATEGORIES.other.color
export const categoryLabel = (slug) => (CATEGORIES[slug] ? translate(CATEGORIES[slug].label) : slug)

/** MapLibre `match` expression: first category -> colour. */
export const categoryMatchExpr = () => [
  'match', ['at', 0, ['get', 'categories']],
  ...Object.entries(CATEGORIES).flatMap(([slug, c]) => [slug, c.color]),
  CATEGORIES.other.color,
]

// "+ Create event" types. Mirrors EVENT_TYPES in backend/app/userevents/__init__.py: type -> category (colour).
export const EVENT_TYPES = {
  club: { label: 'Club', category: 'nightlife' },
  concert: { label: 'Concert', category: 'music' },
  run: { label: 'Run', category: 'running' },
  sport: { label: 'Sport', category: 'sports' },
  studying: { label: 'Studying', category: 'study_buddies' },
  theatre: { label: 'Theatre', category: 'theatre' },
  film: { label: 'Film', category: 'film' },
  exhibition: { label: 'Exhibition', category: 'exhibitions' },
  picnic: { label: 'Picnic', category: 'meetups' },
  meetup: { label: 'Meetup', category: 'meetups' },
  party: { label: 'Party', category: 'nightlife' },
  yoga: { label: 'Yoga', category: 'yoga' },
  games: { label: 'Games', category: 'meetups' },
  other: { label: 'Other', category: 'other' },
}

// Who sees a user event. The first two are public and go onto the Syrenka Users API.
export const AUDIENCES = {
  public: { label: 'Fully public', hint: 'Everyone sees it on the map, anyone can join' },
  public_confirm: { label: 'Public, you confirm', hint: 'Everyone sees it, you approve who joins' },
  friends: { label: 'Friends only', hint: 'Only your friends see it' },
  invite: { label: 'Invitation only', hint: 'Only people you invite see it' },
}
