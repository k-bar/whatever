"""HTTP client for Warsaw Open Data (dane.um.warszawa.pl) REST API."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import re
import urllib3

import requests
from requests.exceptions import SSLError

from src.config import DANE_FILE, get_api_token
from src.external_sources import fetch_streets_gl_venues

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE_URL = "https://dane.um.warszawa.pl/api/action"


@dataclass(frozen=True)
class DatasetSpec:
    """Specification of a Warsaw Open Data or external service endpoint."""

    catalogue_id: str
    key: str
    title: str
    action_name: str

    @property
    def endpoint_url(self) -> str:
        """Return full POST endpoint URL."""
        if self.action_name.startswith("http"):
            return self.action_name
        return f"{API_BASE_URL}/{self.action_name}"


CATALOGUE_DATASETS: dict[str, DatasetSpec] = {
    "00394370-1299-4d98-9910-0983fa7e7612": DatasetSpec(
        catalogue_id="00394370-1299-4d98-9910-0983fa7e7612",
        key="tourist_routes",
        title="Trasy turystyczne",
        action_name="get_sbt_trasy_turystyczne",
    ),
    "59485767-5566-4cb6-9545-a9053efca4ff": DatasetSpec(
        catalogue_id="59485767-5566-4cb6-9545-a9053efca4ff",
        key="toilets",
        title="Toalety",
        action_name="get_m_toalety",
    ),
    "db8077a8-d0e0-480a-af5d-040fb0ea176f": DatasetSpec(
        catalogue_id="db8077a8-d0e0-480a-af5d-040fb0ea176f",
        key="weather",
        title="Pogoda",
        action_name="get_zom_pogoda",
    ),
    "7bc32ffc-c2ac-4d32-83c9-b6f7a0b38de8": DatasetSpec(
        catalogue_id="7bc32ffc-c2ac-4d32-83c9-b6f7a0b38de8",
        key="defibrillators",
        title="Lokalizacja defibrylatorów (AED)",
        action_name="get_scb_lokalizacja_defibrylatorow",
    ),
    "911aa2e8-d021-4dab-b5ff-751079cf902c": DatasetSpec(
        catalogue_id="911aa2e8-d021-4dab-b5ff-751079cf902c",
        key="sports_activities",
        title="Zajęcia sportowe",
        action_name="get_bmm_zajecia_sportowe",
    ),
    "32a0ad2d-06d7-4e9c-acef-17a35c083d8c": DatasetSpec(
        catalogue_id="32a0ad2d-06d7-4e9c-acef-17a35c083d8c",
        key="open_sports_fields",
        title="Otwarte boiska",
        action_name="get_be_otwarte_boiska",
    ),
    "ba202e4b-dfa9-440c-83c0-0b3517520cb8": DatasetSpec(
        catalogue_id="ba202e4b-dfa9-440c-83c0-0b3517520cb8",
        key="city_events",
        title="Kalendarz wydarzeń",
        action_name="get_bmm_kalendarz_wydarzen",
    ),
    "6a7e64d6-b451-4aa5-99d1-2dacece4323b": DatasetSpec(
        catalogue_id="6a7e64d6-b451-4aa5-99d1-2dacece4323b",
        key="air_quality",
        title="Monitoring jakości powietrza",
        action_name="get_bopipk_monitoring_jakosci_powietrza",
    ),
}

EXTERNAL_DATASETS: dict[str, DatasetSpec] = {
    "streets_gl": DatasetSpec(
        catalogue_id="external-streets-gl",
        key="streets_gl",
        title="Miejsca wydarzeń (OpenStreetMap / streets.gl)",
        action_name="https://overpass-api.de/api/interpreter",
    ),
}

DATASETS_BY_KEY: dict[str, DatasetSpec] = {
    **{spec.key: spec for spec in CATALOGUE_DATASETS.values()},
    **EXTERNAL_DATASETS,
}

CATALOGUE_SLUG_PATTERN = re.compile(r"/catalogue/([0-9a-fA-F-]+)")


def _resolve_catalogue_spec(slug: str) -> DatasetSpec:
    """Resolve exact or unique prefix catalogue UUID to DatasetSpec."""
    normalized = slug.lower()
    if normalized in CATALOGUE_DATASETS:
        return CATALOGUE_DATASETS[normalized]
    matches = [
        spec
        for cid, spec in CATALOGUE_DATASETS.items()
        if cid.startswith(normalized)
    ]
    if len(matches) == 1:
        return matches[0]
    raise KeyError(f"Unknown catalogue UUID: {slug}")


def parse_dane_file(dane_path: Path = DANE_FILE) -> list[DatasetSpec]:
    """Read dane.txt and return deduplicated list of DatasetSpec objects."""
    if not dane_path.exists():
        raise FileNotFoundError(f"Catalogue file not found: {dane_path}")

    seen_ids: set[str] = set()
    specs: list[DatasetSpec] = []

    for raw_line in dane_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = CATALOGUE_SLUG_PATTERN.search(line)
        slug = match.group(1) if match else line
        spec = _resolve_catalogue_spec(slug)
        if spec.catalogue_id in seen_ids:
            continue
        seen_ids.add(spec.catalogue_id)
        specs.append(spec)

    return specs


class WarszawaApiClient:
    """Client for fetching datasets from dane.um.warszawa.pl and externals."""

    def __init__(
        self,
        token: Optional[str] = None,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.token = token or get_api_token()
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        """Build HTTP headers with API authorization token."""
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": "WarszawaLiveIngestor/1.0",
        }

    def fetch_spec(
        self,
        spec: DatasetSpec,
        payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Fetch records for a given DatasetSpec."""
        if spec.key == "streets_gl":
            return fetch_streets_gl_venues(session=self.session)

        url = spec.endpoint_url
        headers = self._headers()
        try:
            response = self.session.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except SSLError:
            response = self.session.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
                verify=False,
            )

        response.raise_for_status()
        response.encoding = "utf-8-sig"
        data = response.json()

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, list):
                return [item for item in result if isinstance(item, dict)]
            if isinstance(result, dict):
                return [result]
            return [data]

        raise ValueError(
            f"Unexpected response format from {url}: {type(data).__name__}"
        )

    def fetch_by_key(
        self,
        dataset_key: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Fetch records by dataset key (e.g. 'weather', 'toilets')."""
        if dataset_key not in DATASETS_BY_KEY:
            raise KeyError(f"Unknown dataset key: {dataset_key}")
        return self.fetch_spec(DATASETS_BY_KEY[dataset_key], payload=payload)
