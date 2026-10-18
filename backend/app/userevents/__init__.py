"""User events: things people create from the app's "+ Create event" panel.

Every event a user creates is stored and tracked here (table `user_events`), whoever its audience is.
Events whose audience is public are also published to the "Syrenka Users" source: a normal row in
`events` (+ one occurrence), so they show up in GET /events for everybody, in "APIs I'm plugged in to",
and the existing attendance / join-request endpoints work on them.

Audiences
    public          everyone sees it on the map, anyone can say they're going
    public_confirm  everyone sees it, joining needs the host's OK (join request to the host)
    friends         the host's friends (and invited users)
    invite          only invited users (and the host)

Endpoints (router.py)
    POST   /userevents/photos     {"data_url": "data:image/jpeg;base64,..."} -> {"id", "url"}
    GET    /userevents/photos/{id}  the image
    POST   /userevents            create -> {"event": UserEventOut, "feature": GeoJSON Feature}
    GET    /userevents/mine       events I host, newest first (tracking)
    GET    /userevents/private    FeatureCollection: non-public events I can see (host / invited)
    GET    /userevents/public     FeatureCollection: the "Syrenka Users" API (public user events)
    DELETE /userevents/{id}       host cancels; it disappears from every map
"""

PUBLIC_AUDIENCES = ("public", "public_confirm")
AUDIENCES = (*PUBLIC_AUDIENCES, "friends", "invite")

SOURCE_SLUG = "syrenka-users"
SOURCE_NAME = "Syrenka Users"

# What the form calls an "event type" -> our category (colours, filters, search).
EVENT_TYPES = {
    "club": "nightlife",
    "party": "nightlife",
    "concert": "music",
    "run": "running",
    "sport": "sports",
    "yoga": "yoga",
    "studying": "study_buddies",
    "theatre": "theatre",
    "film": "film",
    "exhibition": "exhibitions",
    "picnic": "meetups",
    "meetup": "meetups",
    "games": "meetups",
    "other": "other",
}
