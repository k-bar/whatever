"""GET /search/events?q=  — only things with a date (kind == "event"), soonest first.

Expected response: {"results": [GeoJSON Feature, ...]}
TODO(backend): same as search.py but filtered to occurrences in [now, now+30d].
"""
