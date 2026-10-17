"""Contract between fetchers (app/ingest/sources/) and the database loader (app/ingest/run.py).

A fetcher never touches the database. It turns a source's records into RawEvent objects;
run.py maps categories, geocodes, filters to Warsaw and upserts.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Occurrence(BaseModel):
    starts_at: datetime  # timezone-aware
    ends_at: datetime | None = None
    daily: bool = False  # True: happens every day between starts_at and ends_at


class RawEvent(BaseModel):
    source_slug: str
    external_key: str  # stable across runs: source URL or id, never a row number
    title: str
    kind: Literal["event", "class", "place"] = "event"
    categories_raw: list[str] = []  # the source's own labels; run.py maps them to app/categories.py
    lead: str | None = None
    text_plain: str | None = None
    text_html: str | None = None
    image_url: str | None = None
    url: str | None = None
    language: str | None = None
    district: str | None = None
    venue_name: str | None = None
    address: str | None = None  # street address; used for geocoding when lat/lng are missing
    lat: float | None = None
    lng: float | None = None
    contact: dict[str, str] = {}  # venue {"phone", "email", "www"}
    occurrences: list[Occurrence] = []
    opening_hours: dict[str, str] | None = None  # places: {"monday": "17:00-22:00", ...}
    audience: list[str] = []
    capacity: int | None = None
    seats_left: int | None = None
    raw: dict = Field(default_factory=dict)  # original record, kept for debugging


@dataclass(frozen=True)
class SourceSpec:
    slug: str
    name: str
    url: str
    # Network call: returns the source's records as plain dicts. Not run in CI.
    fetch_records: Callable[[], list[dict]]
    # Pure function: records -> RawEvents. CI runs it on tests/fixtures/<slug>.json.
    parse: Callable[[list[dict]], list[RawEvent]]
    is_reliable: bool = True

    def fetch(self) -> list[RawEvent]:
        return self.parse(self.fetch_records())
