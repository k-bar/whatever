"""Run Kamil's Open Data synchronizer (src/, repo root) on the EC2 boxes.

src/ is Kamil's code and stays untouched. This launcher only hands it what the box already has:
- the backend's engine: Secrets Manager credentials and the "<DB_SCHEMA>, public" search_path,
  so dev writes into the dev schema (the tables come from alembic 0007);
- a requests.Session that sends dane.um.warszawa.pl calls through the relay (config.py),
  because the API drops connections from AWS IPs.

python -m app.ingest.src_sync            # every dataset once
python -m app.ingest.src_sync --watch    # Kamil's scheduler: weather + air every 10 min, rest every 2 h
"""

import argparse
import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for src/

from src.api_client import API_BASE_URL, DATASETS_BY_KEY, WarszawaApiClient  # noqa: E402
from src.ingestor import DatabaseIngestor  # noqa: E402
from src.scheduler import DatasetScheduler, get_specs_for_group  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402


class RelaySession(requests.Session):
    """Rewrites Warsaw API calls to the relay (same X-Relay-Target protocol as warsaw_open_data.api_request)."""

    def request(self, method, url, *args, headers=None, **kwargs):
        if settings.warsaw_relay_url and str(url).startswith(API_BASE_URL):
            headers = dict(headers or {})
            headers["X-Relay-Target"] = url
            headers["X-Relay-Authorization"] = headers.pop("Authorization", settings.warsaw_api_token or "")
            headers["Authorization"] = f"Bearer {settings.warsaw_relay_token}"
            url = settings.warsaw_relay_url
        return super().request(method, url, *args, headers=headers, **kwargs)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--watch", action="store_true")
    p.add_argument("--group", choices=["fast", "slow", "external", "all"], default="all")
    p.add_argument("--dataset", choices=sorted(DATASETS_BY_KEY))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if not settings.warsaw_api_token:
        raise SystemExit("WARSAW_API_TOKEN is not set")

    client = WarszawaApiClient(token=settings.warsaw_api_token, session=RelaySession())
    ingestor = DatabaseIngestor(engine=engine, api_client=client)
    if args.watch:
        DatasetScheduler(ingestor=ingestor).run_forever()
        return 0

    specs = [DATASETS_BY_KEY[args.dataset]] if args.dataset else get_specs_for_group(args.group)
    failed = 0
    for spec in specs:
        try:
            logging.info("%s: %d records", spec.key, ingestor.sync_spec(spec))
        except Exception:
            failed += 1
            logging.exception("%s: FAILED", spec.key)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
