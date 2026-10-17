"""Address -> (lat, lng) via Nominatim, cached in the geocode_cache table.

Nominatim's policy allows at most 1 request per second, so each run has a budget
and coordinates fill in over a few runs.
"""

import re
import time

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GeocodeCache

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# viewbox = Warsaw bbox; bounded=1 keeps results inside it
VIEWBOX = "20.85,52.37,21.28,52.09"
STREET_PREFIX = re.compile(r"^(ul|al|pl|os|aleja|ulica)\.?\s+", re.I)


class Geocoder:
    def __init__(self, db: Session, budget: int):
        self.db = db
        self.budget = budget
        self.calls = 0
        self._last = 0.0
        self._client = httpx.Client(headers={"User-Agent": settings.nominatim_user_agent}, timeout=20)

    @staticmethod
    def query_for(address: str | None, venue: str | None) -> str | None:
        base = address or venue
        if not base:
            return None
        # Nominatim misses "ul. Elbląska 51" but finds "Elbląska 51"
        base = STREET_PREFIX.sub("", base.strip())
        return base if "warszawa" in base.lower() else f"{base}, Warszawa"

    def lookup(self, query: str) -> tuple[float, float] | None:
        cached = self.db.get(GeocodeCache, query)
        if cached is not None:
            return (cached.lat, cached.lng) if cached.lat is not None else None
        if self.calls >= self.budget:
            return None
        wait = 1.1 - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.calls += 1
        try:
            r = self._client.get(
                NOMINATIM,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "pl",
                    "viewbox": VIEWBOX,
                    "bounded": 1,
                },
            )
            r.raise_for_status()
            hits = r.json()
        except httpx.HTTPError:
            return None  # not cached: retry next run
        point = (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
        self.db.add(GeocodeCache(query=query, lat=point and point[0], lng=point and point[1]))
        self.db.flush()
        return point
