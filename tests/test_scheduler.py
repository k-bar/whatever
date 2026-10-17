"""Unit tests for the 10m/2h scheduler and AWS RDS configuration."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api_client import DatasetSpec  # noqa: E402
from src.config import get_database_url  # noqa: E402
from src.scheduler import (  # noqa: E402
    FAST_INTERVAL_SECONDS,
    SLOW_INTERVAL_SECONDS,
    DatasetScheduler,
    get_interval_seconds,
    get_specs_for_group,
)


def test_aws_rds_database_url_builder() -> None:
    """Verify AWS RDS connection string construction with sslmode=require."""
    aws_env = {
        "DB_HOST": "warszawa-db.c123456789.eu-central-1.rds.amazonaws.com",
        "DB_PORT": "5432",
        "DB_NAME": "warszawa_prod",
        "DB_USER": "admin_user",
        "DB_PASSWORD": "S3cr3t!Pass#1",
    }
    url = get_database_url(env=aws_env)
    assert url == (
        "postgresql+psycopg://admin_user:S3cr3t%21Pass%231"
        "@warszawa-db.c123456789.eu-central-1.rds.amazonaws.com:5432"
        "/warszawa_prod?sslmode=require"
    )


def test_get_specs_for_group_fast_and_slow() -> None:
    """Verify fast group has weather & air_quality and slow has the rest."""
    fast_keys = [s.key for s in get_specs_for_group("fast")]
    slow_keys = [s.key for s in get_specs_for_group("slow")]
    assert set(fast_keys) == {"weather", "air_quality"}
    assert len(slow_keys) == 6
    assert set(fast_keys).isdisjoint(set(slow_keys))


def test_scheduler_ten_minute_and_two_hour_cadence() -> None:
    """Verify scheduler runs fast specs every 600s and slow every 7200s."""
    fake_ingestor: Any = MagicMock()
    fake_ingestor.sync_spec.return_value = 10

    specs = [
        DatasetSpec("id-1", "weather", "Pogoda", "get_zom_pogoda"),
        DatasetSpec("id-2", "air_quality", "Powietrze", "get_bopipk"),
        DatasetSpec("id-3", "toilets", "Toalety", "get_m_toalety"),
    ]
    scheduler = DatasetScheduler(ingestor=fake_ingestor, specs=specs)

    assert get_interval_seconds("weather") == FAST_INTERVAL_SECONDS
    assert get_interval_seconds("toilets") == SLOW_INTERVAL_SECONDS

    # Initial run at t=0: all 3 specs should execute
    res_t0 = scheduler.run_pending(now=0.0)
    assert set(res_t0.keys()) == {"weather", "air_quality", "toilets"}

    # At t=300s (5 min): nothing due yet, 300s remaining until next fast run
    assert scheduler.get_due_specs(now=300.0) == []
    assert scheduler.seconds_until_next(now=300.0) == 300.0

    # At t=600s (10 min): only weather and air_quality are due
    res_t600 = scheduler.run_pending(now=600.0)
    assert set(res_t600.keys()) == {"weather", "air_quality"}

    # At t=7200s (2 hours): both fast and slow specs are due
    res_t7200 = scheduler.run_pending(now=7200.0)
    assert set(res_t7200.keys()) == {"weather", "air_quality", "toilets"}
