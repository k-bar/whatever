"""The search bar's Assistant: answers simple questions about what's on in Warsaw, without an LLM.

    POST /assistant  {"q": "jazz na Pradze w weekend", "lang": "pl", "lat": 52.25, "lng": 21.03,
                      "context": <the previous reply's context, for follow-ups>}
    -> {"answer": "Znalazłem 4 wyniki dla: muzyka · „jazz” · weekend · Praga-Północ ...",
        "results": [GeoJSON Feature, ...], "intent": "find", "understood": "muzyka · ...",
        "area": GeoJSON Feature | null, "context": {...}}

nlu.py reads the question: an intent (find, info, open, company, toilets, AED, weather, air, small talk)
and slots (categories, day / time of day, district or neighbourhood, "near me", leftover words), in
Polish or English, typos tolerated (rapidfuzz). answers.py turns that into a query over the map's tables
and a short reply. The client sends `context` back, so "a jutro?" / "and in Wola?" / "more" keep the rest
of the previous question. lat/lng (optional) is the viewer's position, for "near me" and nearest toilets.
"""
