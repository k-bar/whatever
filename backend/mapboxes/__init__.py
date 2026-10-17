"""Map boxes: the small info card that opens when a pin is clicked.

GET /mapboxes/{event_id} → {"title", "subtitle", "badges": [...], "image", "blocks": [...]}
Block types the UI renders (src/components/MapBox.jsx):
    {"type": "facts",   "items": [{"icon": "clock|pin|map|repeat|users|access|phone", "text": "..."}]}
    {"type": "posters", "items": [{"title", "starts_at", "price", "currency", "availability", "image_url", "url"}]}
    {"type": "social",  "attendees": 3, "wanting": 1, "seats": 2, "capacity": 6, "host": "Ola", "cta": "Ask to join"}
    {"type": "live",    "text": "busy right now", "level": "hot|calm"}
    {"type": "hours",   "text": "Mo-Su 10:00-20:00"}
    {"type": "pitch",   "equipment": [...], "surface": "...", "today": "Od 17:00 do 22:00", "hours": {...}}
    {"type": "text",    "text": "...", "muted": false}
The frontend's src/mapboxes/curate.js produces the same shape locally until this is wired up.
"""
