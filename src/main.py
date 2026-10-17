"""CLI entry point for synchronizing Warsaw Open Data into PostgreSQL."""

import argparse
import logging
from typing import Optional

from sqlalchemy import create_engine

from src.api_client import DATASETS_BY_KEY
from src.config import get_database_url
from src.ingestor import DatabaseIngestor
from src.scheduler import DatasetScheduler, get_specs_for_group


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Fetch Warsaw Open Data from dane.txt into PostgreSQL."
    )
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASETS_BY_KEY.keys()),
        help="Synchronize only a specific dataset key.",
    )
    parser.add_argument(
        "--group",
        choices=["fast", "slow", "external", "all"],
        default="all",
        help=(
            "Synchronize dataset group: 'fast' (weather, air_quality - 10m), "
            "'slow' (other 6 Warsaw datasets - 2h), "
            "'external' (kupbilecik, streets_gl), or 'all'."
        ),
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Run continuous scheduler: weather & air_quality every 10 min, "
            "remaining datasets every 2 hours."
        ),
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Override PostgreSQL DATABASE_URL connection string.",
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize database tables without fetching API data.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Run CLI synchronization workflow."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    args = build_parser().parse_args(argv)
    db_url = args.db_url or get_database_url()
    engine = create_engine(db_url)
    ingestor = DatabaseIngestor(engine=engine)

    ingestor.init_schema()
    if args.init_only:
        logging.info("Database schema initialized successfully.")
        return 0

    if args.watch:
        scheduler = DatasetScheduler(ingestor=ingestor)
        scheduler.run_forever()
        return 0

    if args.dataset:
        spec = DATASETS_BY_KEY[args.dataset]
        logging.info("Synchronizing dataset: %s (%s)", spec.key, spec.title)
        count = ingestor.sync_spec(spec)
        logging.info("Synced %s: %d records", spec.key, count)
        return 0

    specs = get_specs_for_group(args.group)
    for spec in specs:
        logging.info("Synchronizing dataset: %s (%s)", spec.key, spec.title)
        count = ingestor.sync_spec(spec)
        logging.info("Synced %s: %d records", spec.key, count)

    logging.info("Synchronization finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
