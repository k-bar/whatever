# Syrenka.me — frontend

React + Vite + MapLibre GL. One live map of everything social in Warsaw.

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

## How it talks to the backend
`src/data/api.js` calls the FastAPI app (`backend/app`) at `VITE_API_URL` (set per environment by
`deploy/deploy.sh`; locally the vite proxy `/api → http://localhost:8000`). Real data only: no mock
fallback, the map is empty when the API is down. Endpoints used: `GET /events`, `/places`, `/sources`, `/busyareas`,
`/search/{search|events|assistant}`, `/mapboxes/{id}`, `GET|PUT /ui/settings`.

## Interface editor (dev tray)
Top-right sliders button → tray slides in from the right. Every control is declared once in
`src/config/schema.js`; the store (`src/config/store.jsx`) turns values into CSS variables
(`--titleSize`, `--radius`, …) and `data-*` attributes on `<html>` (`data-buttonStyle="glass"`),
which `src/styles/global.css` and the map code read. **Save** persists to localStorage and
`PUT /ui/settings`. To add a knob: add one object to the schema and consume `--id` / `data-id`.
When we leave dev, drop `<InterfaceEditor>` from `App.jsx` (settings keep working).

## Layout
- `components/SearchBar.jsx` – Gemini-style pill: burger (liquid-glass menu), input, mode dropdown
  (Search / Events / Assistant), spyglass. Results slide down under it (desktop) or into the bottom sheet (mobile).
- `components/MapView.jsx` + `mapStyle.js` – MapLibre, OpenFreeMap tiles, palettes / labels / borders / 3D,
  category-coloured circles, starred ring, selected pulse, busy-now heatmap.
- `components/MapBox.jsx` + `mapboxes/curate.js` – info boxes; (+) expands to the right panel, (x) closes;
  the (x) next to the mermaid closes all.
- `components/BottomToolbar.jsx` – venues · busy heatmap · zoom − · home · zoom + · dark · time window.
- `components/BottomSheet.jsx` – mobile half/full-screen sheet for results and boxes.
- `components/SidePanels.jsx` – Profiles, Messages, Favourite spots, "APIs I'm plugged in to".
