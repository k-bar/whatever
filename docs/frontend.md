# Frontend

React 18 + Vite 5 + MapLibre GL + framer-motion. Map tiles come from OpenFreeMap. Owner: Philip
(@philpiano).

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api -> http://localhost:8000
npm run build    # what CI and deploy.sh run
```

## Build-time environment

| Variable | Set by | Meaning |
|---|---|---|
| `VITE_API_URL` | `deploy/deploy.sh` (`API_URL` of the box) | API base. Default `/api`, which only works on the vite dev proxy |
| `VITE_APP_ENV` | `deploy/deploy.sh` (`APP_ENV`: `dev` / `prod`) | `frontend/src/config/env.js` exports it; `DEV_TOOLS = APP_ENV !== 'prod'` |

`deploy.sh` also writes `config.json` (`{apiUrl, env}`) next to the built site.

## Dev tools (never on prod)

Everything below is gated by `DEV_TOOLS`. Vite drops it from the prod bundle.

- **Interface editor tray** (top right). It edits every knob in `src/config/schema.js`: fonts, sizes,
  colours, map palette, layers, marker looks. Settings are saved in `localStorage`.
- **Debug overlay:** zoom level, number of boxes, number of favourites, mobile or desktop.
- **Live API status** in the Data sources panel ("live API · N pins").

Check before a prod promotion:

```bash
cd frontend && VITE_APP_ENV=prod npm run build
grep -c 'debug surface\|data-status\|Saved locally' dist/assets/index-*.js   # must print 0
```

## Layout of `src/`

| Path | What |
|---|---|
| `main.jsx`, `App.jsx` | Entry; App holds the map state, panels, start page and how they hand over to each other |
| `data/api.js` | **The only API client.** Fetches, auth token (`localStorage`), `LoginRequired`, `onAuthChange` |
| `data/categories.js` | Mirror of `backend/app/categories.py`, plus colours |
| `data/social.js`, `data/pinGroups.js` | "I'm going" helpers; which pin option a feature belongs to |
| `config/env.js`, `config/schema.js`, `config/store.jsx` | Environment; the interface editor schema; the store that turns values into CSS variables and `data-*` attributes |
| `components/MapView.jsx`, `mapStyle.js`, `cityLayers.js`, `meMarker.js` | MapLibre map, palettes, toilets / AED / walking-route layers, the "you are here" marker |
| `components/Landing*.jsx` | Start page: hero search (what · when · where), tiles, people network |
| `components/SearchBar.jsx` | Search pill, mode switch, results |
| `components/MapBox.jsx`, `mapboxes/curate.js` | Info boxes on the map and their text |
| `components/SidePanels.jsx` | Slide-over panels: profile, messages, favourites, data sources |
| `components/ProfilePage.jsx` | Profiles, friends, going / been to / hosting, edit profile |
| `components/LoginForm.jsx`, `AccountButton.jsx` | Login / register |
| `components/CreateEventPanel.jsx` | "+ Create event" |
| `components/BottomToolbar.jsx`, `PinMenu.jsx`, `BottomSheet.jsx` | Toolbar, pin options, mobile sheet |
| `components/InterfaceEditor.jsx` | Dev-only editor tray |
| `hooks/` | Favourites (browser when logged out, the account when logged in), media queries, start point |
| `i18n/` | UI strings: English is the key; `pl.js` maps them to Polish |
| `landing/` | Start page search, typeahead and "Syrenka Selects" curation |
| `styles/global.css` | All styles |
| `assets/mermaid.svg` | App icon |

`public/mermaid/` holds the icon variants and `variants.json`. Regenerate them with
`python3 scripts/mermaid_generate.py`, and preview them with `scripts/mermaid_gallery.html`.

## Rules

- **Real data only.** There is no mock fallback, so the map is empty when the API is down.
- **Endpoints:** call only endpoints the backend has (see [api.md](api.md)). If you need a new one,
  open an "API request" issue.
- **Search** runs client-side over the loaded features, and shows only upcoming events.
