"""Live conditions from Warsaw Open Data: weather stations and air quality, latest reading per station.

Ported from Kamil's postgre-aws ingestor (src/ingestor.py: ingest_weather, ingest_air_quality).
Only the latest reading is kept, so the tables stay small. Runs every 10 minutes
(deploy/systemd/warszawa-conditions.timer); status shows up in GET /sources like any source.

python -m app.ingest.conditions
"""

import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ingest.run import get_or_create_source, record_error
from app.ingest.sources.warsaw_open_data import fetch
from app.models import AirStation, WeatherStation
from app.timeutil import WARSAW


@dataclass(frozen=True)
class Feed:
    """A dataset that goes into its own table instead of events (same fields run.py needs)."""

    slug: str
    name: str
    action: str  # dane.um.warszawa.pl API action
    parse: Callable[[list[dict]], list[dict]]  # records -> rows for `model`
    model: type
    key: str  # unique column to upsert on
    url: str = "https://dane.um.warszawa.pl"
    is_reliable: bool = True


def num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def local_time(s: str | None) -> datetime | None:
    """'2026-10-17 19:30:00' (Warsaw local time) -> aware datetime."""
    return datetime.fromisoformat(s).replace(tzinfo=WARSAW) if s else None


def parse_weather(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        if not r.get("lokalizacja") or num(r.get("lat")) is None or num(r.get("lon")) is None:
            continue
        wind_dir = num(r.get("kier_wiatru"))
        rows.append(
            dict(
                name=r["lokalizacja"],
                lat=num(r["lat"]),
                lng=num(r["lon"]),
                measured_at=local_time(r.get("czas")),
                temp_air=num(r.get("temp_pow")),
                temp_road=num(r.get("temp_naw")),
                humidity=num(r.get("wilg_pow")),
                wind_speed=num(r.get("pred_wiatru")),
                wind_dir=int(wind_dir) if wind_dir is not None else None,
                precipitation=num(r.get("int_opadu")),
            )
        )
    return rows


def parse_air(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        if not r.get("name") or num(r.get("lat")) is None or num(r.get("lon")) is None:
            continue
        params: dict[str, dict] = {}
        for d in r.get("data") or []:
            code, when = d.get("param_code"), d.get("time") or ""
            if not code or (code in params and params[code]["time"] >= when):
                continue  # keep the latest value per parameter
            params[code] = {
                "name": d.get("param_name"),
                "value": num(d.get("value")),
                "unit": d.get("unit"),
                "index": (d.get("ijp") or {}).get("name"),
                "time": when,
            }
        latest = max((p["time"] for p in params.values() if p["time"]), default=None)
        address, index = r.get("address") or {}, r.get("ijp") or {}
        rows.append(
            dict(
                name=r["name"],
                station=r.get("station"),
                lat=num(r["lat"]),
                lng=num(r["lon"]),
                district=address.get("district"),
                street=address.get("street"),
                index_name=index.get("name"),
                recommendation=index.get("recommendations"),
                params=params,
                measured_at=local_time(latest),
            )
        )
    return rows


def sync(db: Session, feed: Feed, records: list[dict] | None = None) -> int:
    """Fetch (unless records are given), upsert on feed.key, record status. Caller commits."""
    rows = feed.parse(fetch(feed.action) if records is None else records)
    rows = list({row[feed.key]: row for row in rows}.values())  # one upsert per key per statement
    if rows:
        stmt = insert(feed.model).values(rows)
        cols = {c: stmt.excluded[c] for c in rows[0] if c != feed.key}
        db.execute(
            stmt.on_conflict_do_update(index_elements=[feed.key], set_=cols | {"updated_at": func.now()})
        )
    source = get_or_create_source(db, feed)
    source.last_run_at = datetime.now(UTC)
    source.last_status = "ok"
    source.last_error = None
    source.item_count = len(rows)
    return len(rows)


def run_feeds(feeds: list[Feed]) -> int:
    """Sync each feed in its own transaction; returns the number that failed."""
    failed = 0
    for feed in feeds:
        with SessionLocal() as db:
            try:
                n = sync(db, feed)
                db.commit()
                print(f"{feed.slug}: {n} stored")
            except Exception:
                db.rollback()
                failed += 1
                err = traceback.format_exc()
                print(f"{feed.slug}: FAILED\n{err}", file=sys.stderr)
                record_error(db, feed, err)
    return failed


FEEDS = [
    Feed(
        slug="warsaw_weather",
        name="Warsaw Open Data – weather stations",
        action="get_zom_pogoda",
        parse=parse_weather,
        model=WeatherStation,
        key="name",
    ),
    Feed(
        slug="warsaw_air",
        name="Warsaw Open Data – air quality",
        action="get_bopipk_monitoring_jakosci_powietrza",
        parse=parse_air,
        model=AirStation,
        key="name",
    ),
]


if __name__ == "__main__":
    sys.exit(1 if run_feeds(FEEDS) else 0)
