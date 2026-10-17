"""Fetcher contract: every registered source must parse its fixture into valid RawEvents.

No network, no database. Adding a source? Save some real records as tests/fixtures/<slug>.json.
"""

import pytest

from app.ingest.base import RawEvent
from app.ingest.sources import SOURCES
from tests.conftest import FIXTURES, fixture_records


@pytest.fixture(autouse=True)
def clean_db():  # override: contract tests don't touch the DB
    yield


@pytest.mark.parametrize("slug", sorted(SOURCES))
def test_fixture_exists(slug):
    assert (FIXTURES / f"{slug}.json").exists(), f"add tests/fixtures/{slug}.json with sample records"


@pytest.mark.parametrize("slug", sorted(SOURCES))
def test_parser_output(slug):
    events = SOURCES[slug].parse(fixture_records(slug))
    assert events, "parser returned nothing for the fixture"
    assert all(isinstance(e, RawEvent) for e in events)
    assert all(e.source_slug == slug for e in events), "source_slug must match the registry key"
    keys = [e.external_key for e in events]
    assert len(keys) == len(set(keys)), "external_key must be unique within a source"
    for e in events:
        assert e.title.strip()
        for occ in e.occurrences:
            assert occ.starts_at.tzinfo is not None, "datetimes must be timezone-aware"
            assert occ.ends_at is None or occ.ends_at >= occ.starts_at
        if e.lat is not None:
            assert 52.0 < e.lat < 52.5 and 20.7 < e.lng < 21.4, "lat/lng swapped or outside Warsaw"


def test_parser_is_deterministic():
    for slug, spec in SOURCES.items():
        a = [e.external_key for e in spec.parse(fixture_records(slug))]
        b = [e.external_key for e in spec.parse(fixture_records(slug))]
        assert a == b, slug
