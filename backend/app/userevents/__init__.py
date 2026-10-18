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

Endpoints (router.py; the parts other modules use, like can_see and publish, are in service.py)
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
    # Every pin type in the app (frontend/src/data/types.js), so an invite can be any type at all
    "museum": "exhibitions",
    "gallery": "exhibitions",
    "cinema": "film",
    "culture_centre": "culture",
    "library": "education",
    "venue": "culture",
    "festival": "festivals",
    "nightlife": "nightlife",
    "performance": "theatre",
    "screening": "film",
    "education": "education",
    "kids": "family",
    "market": "markets",
    "business": "business",
    "community": "meetups",
    "charity": "meetups",
    "tour": "culture",
    "celebration": "festivals",
    "sports_class": "sports",
    "fitness": "sports",
    "dance": "sports",
    "mind_body": "yoga",
    "running": "running",
    "pitch": "sports",
    "sports_venue": "sports",
    "competition": "sports",
    "hobby_club": "meetups",
    "social_club": "meetups",
    "restaurant": "food",
    "cafe": "food",
    "alcohol": "nightlife",
}
