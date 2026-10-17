"""Load Mateusz's events.db / sport.db snapshots (made by fetch_data.py) into Postgres.

Uses the stored raw_json with the same parsers as the live fetchers, so no API token is needed.

    python scripts/import_sqlite.py db/events.db db/sport.db [--geocode-limit 0]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.ingest.geocode import Geocoder  # noqa: E402
from app.ingest.run import load  # noqa: E402
from app.ingest.sources import SOURCES  # noqa: E402

TABLES = {"events": "warsaw_events", "sport_classes": "warsaw_sport", "open_pitches": "warsaw_pitches"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--geocode-limit", type=int, default=0)
    args = ap.parse_args()

    for path in args.files:
        con = sqlite3.connect(path)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, slug in TABLES.items():
            if table not in tables:
                continue
            records = [json.loads(r[0]) for r in con.execute(f"SELECT raw_json FROM {table}")]
            spec = SOURCES[slug]
            with SessionLocal() as db:
                geocoder = Geocoder(db, args.geocode_limit) if args.geocode_limit else None
                n = load(db, spec, spec.parse(records), geocoder)
                db.commit()
            print(f"{path.name}:{table} -> {slug}: {len(records)} records, {n} stored")


if __name__ == "__main__":
    main()
