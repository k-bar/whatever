"""OpenStreetMap's Overpass API, shared by the osm_* sources (venues, restaurants, transit)."""

import json
import urllib.parse
import urllib.request

from app.config import settings

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def overpass(query: str) -> list[dict]:
    """The query's elements, from the first mirror that answers in full.

    A busy mirror can answer HTTP 200 with a "remark" (e.g. "runtime error: Query timed out") and no
    or partial elements; that counts as a failure, or the sources would be emptied off the map.
    """
    body = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | str | None = None
    for url in OVERPASS_URLS:  # mirrors share the load; try the next one if busy
        req = urllib.request.Request(url, data=body, headers={"User-Agent": settings.nominatim_user_agent})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError) as e:
            last_error = e
            continue
        if data.get("remark"):
            last_error = data["remark"]
            continue
        return data.get("elements", [])
    raise RuntimeError(f"all Overpass mirrors failed: {last_error}")
