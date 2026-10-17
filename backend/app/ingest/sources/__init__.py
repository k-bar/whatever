"""Registry of all fetchers. To add a source:

1. Create app/ingest/sources/<name>.py with a list SPECS of SourceSpec (see warsaw_open_data.py).
2. Import it below and add its SPECS.
3. Save a few real records as tests/fixtures/<slug>.json so CI can check your parser.
"""

from app.ingest.base import SourceSpec
from app.ingest.sources import osm_venues, warsaw_amenities, warsaw_open_data

SOURCES: dict[str, SourceSpec] = {
    spec.slug: spec for spec in [*warsaw_open_data.SPECS, *warsaw_amenities.SPECS, *osm_venues.SPECS]
}
