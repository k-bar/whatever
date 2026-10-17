# API reference

- **Base URLs:** `https://api.syrenka.me` (prod, schema `public`) and `https://api-dev.syrenka.me` (dev,
  schema `dev`). Locally `http://localhost:8000`; the vite dev server proxies `/api` to it.
- **Source of truth:** `<base>/docs` (Swagger UI) and `<base>/openapi.json`. This page is a map of what
  exists and who uses it.
- **Auth:** `POST /auth/login` or `/auth/register` returns `access_token`, a JWT valid for 7 days. Send
  it as `Authorization: Bearer <token>`. 🔒 marks endpoints that need a login. 👤 marks endpoints where
  a login changes the answer (`get_optional_user`).
- **Map data** is GeoJSON: a `FeatureCollection` of Points, or LineStrings for routes.
- **`lang=pl|en`** returns titles and leads in that language when a translation exists.

## Meta

| Method | Path | What |
|---|---|---|
| GET | `/health` | `{status, env, sha}`; the deploy script waits for its own sha here |
| GET | `/categories` | Category slugs and labels |
| GET | `/sources` | Backend ingest status per source |

## Map

| Method | Path | What | Main parameters |
|---|---|---|---|
| GET | `/events` | One feature per occurrence (events and classes) | `bbox=w,s,e,n`, `from` (default now), `to` (default from + 30 days), `category` (repeatable), `kind=event\|class`, `q`, `include_unlocated`, `limit` (default 500), `lang` |
| GET | `/events/now` | Starting near a point within a few hours | `lat`, `lng`, `radius_m` (default 3000), `hours` (default 3), `lang` |
| GET | `/events/{id}` | One event, class or place with its occurrences | `past=true` to include finished ones, `lang` |
| POST 🔒 | `/events` | Create an invitation (host auto-attends) | body `InviteIn` |
| GET | `/places` | Venues and pitches; toilets and AEDs only when asked for with `category` | `bbox`, `category` (repeatable), `q`, `open_now`, `lang` |
| GET | `/conditions` | `{weather, air}`: latest reading per station | |
| GET | `/routes` | Tourist routes as LineStrings | |
| GET | `/busyareas` | "Busy areas" polygons (committed GeoJSON) | |

## Accounts and profiles

| Method | Path | What |
|---|---|---|
| POST | `/auth/register` | `email`, `password` (≥ 8), `display_name`, optional `username`; 409 when the email or username is taken |
| POST | `/auth/login` | `email`, `password` |
| GET 🔒 | `/me` | My account, including `email`, `created_at`, `favourite_ids` |
| PATCH 🔒 | `/me` | `display_name`, `username`, `gender` (`f`/`m`, `""` clears it), `bio` (`null` clears it), `photos` (http(s) URL or `/userevents/photos/<id>`; `photos[0]` is the profile picture), `interests`, `links`, `hangouts` (≤ 5) |
| GET/PUT 🔒 | `/me/favourites` | Favourited `events.id` list; PUT replaces it (≤ 1000, unknown ids dropped) |
| GET | `/users/{id}` | Public profile (never includes email) |
| GET 👤 | `/users/{id}/profile`, `/profiles/{username}` | Profile page: stats, `relation` to the viewer, `can_see_events` |
| GET 👤 | `/users/{id}/events?scope=going\|been\|hosting` | Event lists; 403 unless it's you or a friend |
| GET 👤 | `/users/{id}/friends` | Friends list |
| GET 👤 | `/usernames/{username}/available` | Live @username check |
| GET 👤 | `/people/search?q=` | @username prefix, then display names; max 10 |

## Friends

| Method | Path | What |
|---|---|---|
| POST 🔒 | `/friends/requests` | Ask `username` to be friends; accepts at once if they already asked you |
| GET 🔒 | `/me/friend-requests?direction=incoming\|outgoing` | Pending requests |
| PATCH 🔒 | `/friend-requests/{id}` | `accepted` / `declined`; only the addressee can decide |
| DELETE 🔒 | `/friends/{user_id}` | Unfriend, or withdraw or decline a pending request |

## "I'm going, come with me"

| Method | Path | What |
|---|---|---|
| PUT 🔒 | `/occurrences/{id}/attendance` | I'm going; `wants_company`, `max_group` |
| DELETE 🔒 | `/occurrences/{id}/attendance` | Not going any more |
| GET 🔒 | `/occurrences/{id}/attendees` | Who's going (`wants_company` filter) |
| GET 🔒 | `/me/attending` | My attendance, with `event_id`, `title`, `starts_at`, `ends_at` |
| POST 🔒 | `/occurrences/{id}/join-requests` | Ask a person who wants company, or the host, to join them |
| GET 🔒 | `/me/join-requests` | Incoming + pending = the "swipe deck" |
| PATCH 🔒 | `/join-requests/{id}` | Accept / reject; only the receiver can decide. Accepting reveals contact links |

## User-created events (`/userevents`)

| Method | Path | What |
|---|---|---|
| POST 🔒 | `/userevents/photos` | Upload a photo (`data_url`); returns its id and URL |
| GET | `/userevents/photos/{id}` | The photo |
| POST 🔒 | `/userevents` | Create an event; public ones also appear in `GET /events` |
| GET 🔒 | `/userevents/mine` | Everything I created, with status |
| GET 🔒 | `/userevents/private` | Non-public events I host or am invited to |
| GET | `/userevents/public` | Upcoming public user events |
| DELETE 🔒 | `/userevents/{id}` | Host cancels (kept in history, removed from maps) |

## Who calls what

`frontend/src/data/api.js` is the only API client in the UI. It calls:
- **Map:** `/events`, `/places`, `/places?category=toilets|aed`, `/routes`, `/busyareas`, `/sources`
- **Accounts:** `/auth/*`, `/me`, `/me/favourites`
- **Social:** `/occurrences/*/attendance`, `/occurrences/*/join-requests`, `/me/join-requests`
- **Profiles and friends:** the profile, friend and people endpoints
- **User events:** `/userevents*`

Not called by the UI yet: `/events/now`, `/events/{id}`, `POST /events`, `/conditions`,
`/userevents/public`, `/userevents/mine`, `/categories`.

Kamil's raw tables have no endpoints.
