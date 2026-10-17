"""Periodic scheduler and AWS Lambda handler for Warsaw Open Data sync."""

import logging
import signal
import time
from types import FrameType
from typing import Any, Optional

from sqlalchemy import create_engine

from src.api_client import DATASETS_BY_KEY, DatasetSpec, parse_dane_file
from src.config import get_database_url
from src.ingestor import DatabaseIngestor

FAST_INTERVAL_SECONDS = 10 * 60  # 10 minutes
SLOW_INTERVAL_SECONDS = 2 * 60 * 60  # 2 hours

FAST_DATASET_KEYS: frozenset[str] = frozenset({"weather", "air_quality"})


def get_interval_seconds(dataset_key: str) -> int:
    """Return refresh interval in seconds for a given dataset key."""
    if dataset_key in FAST_DATASET_KEYS:
        return FAST_INTERVAL_SECONDS
    return SLOW_INTERVAL_SECONDS


def get_specs_for_group(
    group: str,
    specs: Optional[list[DatasetSpec]] = None,
) -> list[DatasetSpec]:
    """Filter dataset specs by schedule group ('fast', 'slow', or 'all')."""
    all_specs = specs if specs is not None else parse_dane_file()
    if group == "all":
        return list(all_specs)
    if group == "fast":
        return [s for s in all_specs if s.key in FAST_DATASET_KEYS]
    if group == "slow":
        return [s for s in all_specs if s.key not in FAST_DATASET_KEYS]
    raise ValueError(f"Unknown schedule group: {group}")


class DatasetScheduler:
    """In-process scheduler running fast (10m) and slow (2h) dataset syncs."""

    def __init__(
        self,
        ingestor: DatabaseIngestor,
        specs: Optional[list[DatasetSpec]] = None,
    ) -> None:
        self.ingestor = ingestor
        self.specs = specs if specs is not None else parse_dane_file()
        self.last_run: dict[str, float] = {}
        self._stop_requested = False

    def request_stop(self) -> None:
        """Signal the scheduler loop to exit cleanly."""
        self._stop_requested = True

    def get_due_specs(self, now: float) -> list[DatasetSpec]:
        """Return datasets that are due for synchronization at timestamp."""
        due: list[DatasetSpec] = []
        for spec in self.specs:
            last = self.last_run.get(spec.key)
            interval = get_interval_seconds(spec.key)
            if last is None or (now - last) >= interval:
                due.append(spec)
        return due

    def run_pending(
        self, now: Optional[float] = None
    ) -> dict[str, int]:
        """Synchronize all currently due datasets and update timestamps."""
        current_time = time.monotonic() if now is None else now
        due_specs = self.get_due_specs(current_time)
        results: dict[str, int] = {}

        for spec in due_specs:
            if self._stop_requested:
                break
            try:
                logging.info(
                    "Scheduler syncing %s (%s)...", spec.key, spec.title
                )
                count = self.ingestor.sync_spec(spec)
                results[spec.key] = count
                logging.info(
                    "Scheduler synced %s: %d records", spec.key, count
                )
            except Exception as exc:
                logging.error(
                    "Scheduler error on %s: %s", spec.key, exc
                )
            finally:
                self.last_run[spec.key] = current_time

        return results

    def seconds_until_next(self, now: Optional[float] = None) -> float:
        """Return seconds remaining until the earliest dataset is due."""
        current_time = time.monotonic() if now is None else now
        if not self.specs:
            return float(FAST_INTERVAL_SECONDS)

        wait_times: list[float] = []
        for spec in self.specs:
            last = self.last_run.get(spec.key)
            if last is None:
                return 0.0
            interval = get_interval_seconds(spec.key)
            remaining = (last + interval) - current_time
            wait_times.append(max(0.0, remaining))

        return min(wait_times)

    def run_forever(self, max_sleep_chunk: float = 5.0) -> None:
        """Run continuous scheduling loop until interrupted."""
        def _handle_sig(signum: int, _frame: Optional[FrameType]) -> None:
            logging.info("Received signal %d, stopping scheduler...", signum)
            self.request_stop()

        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)

        logging.info(
            "Starting scheduler: fast=%ds (weather, air_quality), slow=%ds",
            FAST_INTERVAL_SECONDS,
            SLOW_INTERVAL_SECONDS,
        )
        while not self._stop_requested:
            self.run_pending()
            wait_sec = self.seconds_until_next()
            slept = 0.0
            while not self._stop_requested and slept < wait_sec:
                step = min(max_sleep_chunk, wait_sec - slept)
                time.sleep(step)
                slept += step


def lambda_handler(
    event: Optional[dict[str, Any]],
    context: Any = None,
) -> dict[str, Any]:
    """AWS Lambda entry point triggered by AWS EventBridge Scheduler."""
    del context
    payload = event if isinstance(event, dict) else {}
    engine = create_engine(get_database_url())
    ingestor = DatabaseIngestor(engine=engine)
    ingestor.init_schema()

    dataset_key = payload.get("dataset")
    if isinstance(dataset_key, str) and dataset_key:
        spec = DATASETS_BY_KEY[dataset_key]
        count = ingestor.sync_spec(spec)
        return {"statusCode": 200, "synced": {spec.key: count}}

    group = str(payload.get("group", "all"))
    specs = get_specs_for_group(group)
    synced: dict[str, int] = {}
    for spec in specs:
        synced[spec.key] = ingestor.sync_spec(spec)

    return {"statusCode": 200, "group": group, "synced": synced}
