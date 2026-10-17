"""GET /search/assistant?q=  — natural-language question, answered with the data.

Expected response: {"answer": "text shown in the results panel", "results": [GeoJSON Feature, ...]}
TODO(backend): LLM call with the matching features as context; keep `results` so the map
can still highlight what the answer talks about.
"""
