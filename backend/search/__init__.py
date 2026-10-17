"""Search endpoints behind the search bar's mode dropdown (Search / Events / Assistant).

The frontend calls GET /search/<mode>?q=... (src/data/api.js → runSearch) and expects:
    {"results": [GeoJSON Feature, ...], "answer": "optional text (assistant only)"}
Until these are wired into app/main.py the frontend filters client-side.
"""
