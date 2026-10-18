"""Registry of all fetchers. To add a source:

1. Create app/ingest/sources/<name>.py with a list SPECS of SourceSpec (see warsaw_open_data.py).
2. Import it below and add its SPECS.
3. Save a few real records as tests/fixtures/<slug>.json so CI can check your parser.
"""

from app.ingest.base import SourceSpec
from app.ingest.sources import (
    osm_restaurants,
    osm_transit,
    osm_venues,
    songkick,
    warsaw_amenities,
    warsaw_open_data,
    waw4free,
)

SOURCES: dict[str, SourceSpec] = {
    spec.slug: spec
    for spec in [
        *warsaw_open_data.SPECS,
        *warsaw_amenities.SPECS,
        *osm_venues.SPECS,
        *osm_restaurants.SPECS,
        *osm_transit.SPECS,
        *songkick.SPECS,
        *waw4free.SPECS,
    ]
}
