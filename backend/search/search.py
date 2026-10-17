"""GET /search/search?q=  — places, venues, districts, events: everything, ranked.

Expected response: {"results": [GeoJSON Feature, ...]}  (same features as GET /events + /places)
TODO(backend): full-text over title / venue_name / lead / district, bbox optional.
"""
