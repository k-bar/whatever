"""Data transformation and PostgreSQL ingestion for Warsaw Open Data."""

from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import Engine, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.api_client import DatasetSpec, WarszawaApiClient, parse_dane_file
from src.models import (
    AirQualityMeasurement,
    AirQualityStation,
    Base,
    CityEvent,
    Defibrillator,
    EntertainmentEvent,
    OpenSportsField,
    Restaurant,
    SportsActivity,
    StreetsGlVenue,
    SyncLog,
    Toilet,
    TouristPoint,
    TouristRoute,
    WeatherMeasurement,
    utc_now,
)


def _to_float(val: Any) -> Optional[float]:
    """Convert value to float or return None if invalid."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val: Any) -> Optional[int]:
    """Convert value to int or return None if invalid."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _to_str(val: Any) -> Optional[str]:
    """Convert value to stripped string or None."""
    if val is None:
        return None
    text = str(val).strip()
    return text if text else None


def _parse_dt(val: Any) -> Optional[datetime]:
    """Parse ISO-like timestamp string into naive datetime."""
    text = _to_str(val)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError:
        return None


def _extract_lon_lat(
    geometry: Optional[dict[str, Any]],
) -> tuple[Optional[float], Optional[float]]:
    """Extract (lon, lat) from GeoJSON geometry object."""
    if not isinstance(geometry, dict):
        return None, None
    coords: Any = geometry.get("coordinates")
    while (
        isinstance(coords, list)
        and len(coords) > 0
        and isinstance(coords[0], list)
    ):
        coords = coords[0]
    if isinstance(coords, list) and len(coords) >= 2:
        return _to_float(coords[0]), _to_float(coords[1])
    return None, None


def ingest_tourist_routes(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert tourist routes and associated tourist points."""
    now = utc_now()
    routes_by_title: dict[str, dict[str, Any]] = {}
    points_by_id: dict[int, dict[str, Any]] = {}

    for item in records:
        title = _to_str(item.get("title"))
        if not title:
            continue
        raw_points = item.get("tourist_points")
        t_points = raw_points if isinstance(raw_points, list) else []
        traces = item.get("traces")
        routes_by_title[title] = {
            "title": title,
            "length_km": _to_float(item.get("length")),
            "description": _to_str(item.get("description")),
            "traces": traces if isinstance(traces, list) else [],
            "tourist_points": t_points,
            "updated_at": now,
        }
        for pt in t_points:
            if not isinstance(pt, dict):
                continue
            pt_id = _to_int(pt.get("id_point"))
            pt_name = _to_str(pt.get("name"))
            if pt_id is None or not pt_name:
                continue
            latlng = pt.get("latlng")
            lat_val = (
                _to_float(latlng.get("lat"))
                if isinstance(latlng, dict)
                else None
            )
            lng_val = (
                _to_float(latlng.get("lng"))
                if isinstance(latlng, dict)
                else None
            )
            points_by_id[pt_id] = {
                "id_point": pt_id,
                "name": pt_name,
                "city": _to_str(pt.get("city")),
                "lat": lat_val,
                "lng": lng_val,
                "updated_at": now,
            }

    if routes_by_title:
        bind = session.get_bind()
        col_names = {
            c["name"] for c in inspect(bind).get_columns("tourist_routes")
        }
        if "traces" in col_names:
            stmt = pg_insert(TouristRoute).values(
                list(routes_by_title.values())
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["title"],
                set_={
                    "length_km": stmt.excluded.length_km,
                    "description": stmt.excluded.description,
                    "traces": stmt.excluded.traces,
                    "tourist_points": stmt.excluded.tourist_points,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)

    if points_by_id:
        p_stmt = pg_insert(TouristPoint).values(list(points_by_id.values()))
        p_stmt = p_stmt.on_conflict_do_update(
            index_elements=["id_point"],
            set_={
                "name": p_stmt.excluded.name,
                "city": p_stmt.excluded.city,
                "lat": p_stmt.excluded.lat,
                "lng": p_stmt.excluded.lng,
                "updated_at": p_stmt.excluded.updated_at,
            },
        )
        session.execute(p_stmt)

    return len(routes_by_title)


def ingest_toilets(session: Session, records: list[dict[str, Any]]) -> int:
    """Upsert public toilet locations."""
    now = utc_now()
    rows_by_key: dict[tuple[str, float, float], dict[str, Any]] = {}

    for item in records:
        lon, lat = _extract_lon_lat(item.get("geometry"))
        props = item.get("properties")
        if not isinstance(props, dict) or lon is None or lat is None:
            continue
        lokalizacja = _to_str(props.get("lokalizacja")) or "Nieznana"
        key = (lokalizacja, lon, lat)
        rows_by_key[key] = {
            "zarzadca": _to_str(props.get("zarzadca")),
            "typ": _to_str(props.get("typ")),
            "lokalizacja": lokalizacja,
            "dzielnica": _to_str(props.get("dzielnica")),
            "dostepnosc": _to_int(
                props.get("dostepnosc", props.get("Dostępność"))
            ),
            "platnosc": _to_int(
                props.get("platnosc", props.get("Płatność"))
            ),
            "przewijak": _to_int(
                props.get("przewijak", props.get("Przewijak"))
            ),
            "aktu_dan": _to_str(props.get("aktu_dan")),
            "poch_dan": _to_str(props.get("poch_dan")),
            "godziny": _to_str(props.get("godziny")),
            "uwagi": _to_str(props.get("uwagi")),
            "lon": lon,
            "lat": lat,
            "updated_at": now,
        }

    if rows_by_key:
        stmt = pg_insert(Toilet).values(list(rows_by_key.values()))
        stmt = stmt.on_conflict_do_update(
            constraint="uq_toilets_loc_coords",
            set_={
                "zarzadca": stmt.excluded.zarzadca,
                "typ": stmt.excluded.typ,
                "dzielnica": stmt.excluded.dzielnica,
                "dostepnosc": stmt.excluded.dostepnosc,
                "platnosc": stmt.excluded.platnosc,
                "przewijak": stmt.excluded.przewijak,
                "aktu_dan": stmt.excluded.aktu_dan,
                "poch_dan": stmt.excluded.poch_dan,
                "godziny": stmt.excluded.godziny,
                "uwagi": stmt.excluded.uwagi,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        session.execute(stmt)

    return len(rows_by_key)


def ingest_weather(session: Session, records: list[dict[str, Any]]) -> int:
    """Append historical weather measurements (ignoring duplicates)."""
    now = utc_now()
    rows_by_key: dict[tuple[str, datetime], dict[str, Any]] = {}

    for item in records:
        lokalizacja = _to_str(
            item.get("lokalizacja", item.get("Lokalizacja"))
        )
        czas = _parse_dt(item.get("czas"))
        if not lokalizacja or czas is None:
            continue
        rows_by_key[(lokalizacja, czas)] = {
            "lokalizacja": lokalizacja,
            "lat": _to_float(item.get("lat")),
            "lon": _to_float(item.get("lon")),
            "czas": czas,
            "temp_pow": _to_float(item.get("temp_pow")),
            "temp_naw": _to_float(item.get("temp_naw")),
            "wilg_pow": _to_float(item.get("wilg_pow")),
            "pred_wiatru": _to_float(item.get("pred_wiatru")),
            "kier_wiatru": _to_float(item.get("kier_wiatru")),
            "int_opadu": _to_float(item.get("int_opadu")),
            "fetched_at": now,
        }

    if rows_by_key:
        stmt = pg_insert(WeatherMeasurement).values(
            list(rows_by_key.values())
        )
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_weather_station_time"
        )
        session.execute(stmt)

    return len(rows_by_key)


def ingest_defibrillators(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert AED defibrillator records by defibrillator_id."""
    now = utc_now()
    rows_by_id: dict[str, dict[str, Any]] = {}

    for item in records:
        lon, lat = _extract_lon_lat(item.get("geometry"))
        props = item.get("properties")
        if not isinstance(props, dict):
            continue
        defib_id = _to_str(props.get("defibrillator_id"))
        if not defib_id:
            continue
        rows_by_id[defib_id] = {
            "defibrillator_id": defib_id,
            "lon": lon,
            "lat": lat,
            "device_access_description": _to_str(
                props.get("device_access_description")
            ),
            "device_availability": _to_str(props.get("device_availability")),
            "device_location": _to_str(props.get("device_location")),
            "device_manufacturer": _to_str(props.get("device_manufacturer")),
            "device_public_access": _to_str(props.get("device_public_access")),
            "device_specifications": _to_str(
                props.get("device_specifications")
            ),
            "location_building": _to_str(props.get("location_building")),
            "location_city": _to_str(props.get("location_city")),
            "location_description": _to_str(props.get("location_description")),
            "location_object_name": _to_str(props.get("location_object_name")),
            "location_postcode": _to_str(props.get("location_postcode")),
            "location_street": _to_str(props.get("location_street")),
            "updated_at": now,
        }

    if rows_by_id:
        stmt = pg_insert(Defibrillator).values(list(rows_by_id.values()))
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in rows_by_id[next(iter(rows_by_id))].keys()
            if col != "defibrillator_id"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["defibrillator_id"],
            set_=update_cols,
        )
        session.execute(stmt)

    return len(rows_by_id)


def ingest_sports_activities(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert sports activities by URL."""
    now = utc_now()
    rows_by_url: dict[str, dict[str, Any]] = {}

    for item in records:
        url = _to_str(item.get("url"))
        title = _to_str(item.get("title"))
        if not url or not title:
            continue
        rows_by_url[url] = {
            "url": url,
            "title": title,
            "time": _to_str(item.get("time")),
            "text": _to_str(item.get("text")),
            "language": _to_str(item.get("language")),
            "category": (
                item.get("category")
                if isinstance(item.get("category"), list)
                else None
            ),
            "day": (
                item.get("day") if isinstance(item.get("day"), list) else None
            ),
            "dedicated": (
                item.get("dedicated")
                if isinstance(item.get("dedicated"), list)
                else None
            ),
            "localization": (
                item.get("localization")
                if isinstance(item.get("localization"), list)
                else None
            ),
            "address": (
                item.get("address")
                if isinstance(item.get("address"), list)
                else None
            ),
            "image": (
                item.get("image")
                if isinstance(item.get("image"), dict)
                else None
            ),
            "updated_at": now,
        }

    if rows_by_url:
        stmt = pg_insert(SportsActivity).values(list(rows_by_url.values()))
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in rows_by_url[next(iter(rows_by_url))].keys()
            if col != "url"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["url"],
            set_=update_cols,
        )
        session.execute(stmt)

    return len(rows_by_url)


def ingest_open_sports_fields(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert open school sports fields."""
    now = utc_now()
    rows_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for item in records:
        nazwa = _to_str(item.get("Nazwa placówki oświatowej"))
        adres = _to_str(item.get("Adres obiektu"))
        typ = _to_str(item.get("Typ obiektu")) or "nieznany"
        wyposazenie = _to_str(item.get("Boisk uniwersalne zawiera")) or ""
        if not nazwa or not adres:
            continue
        key = (nazwa, adres, typ, wyposazenie)
        rows_by_key[key] = {
            "dzielnica": _to_str(item.get("Dzielnica")),
            "adres_obiektu": adres,
            "nazwa_placowki": nazwa,
            "typ_obiektu": typ,
            "wyposazenie": wyposazenie,
            "rodzaj_nawierzchni": _to_str(item.get("Rodzaj nawierzchni")),
            "trybuny": _to_str(item.get("Obiekt wyposażony w trybuny")),
            "pilkochwyty": _to_str(
                item.get("Obiekt wyposażony w piłkochwyty")
            ),
            "poniedzialek": _to_str(item.get("Poniedziałek")),
            "wtorek": _to_str(item.get("Wtorek")),
            "sroda": _to_str(item.get("Środa")),
            "czwartek": _to_str(item.get("Czwartek")),
            "piatek": _to_str(item.get("Piątek")),
            "sobota": _to_str(item.get("Sobota")),
            "niedziela": _to_str(item.get("Niedziela")),
            "uwagi": _to_str(item.get("Uwagi")),
            "data_aktualizacji": _to_str(item.get("Data aktualizacji")),
            "updated_at": now,
        }

    if rows_by_key:
        stmt = pg_insert(OpenSportsField).values(list(rows_by_key.values()))
        exclude_keys = {
            "nazwa_placowki",
            "adres_obiektu",
            "typ_obiektu",
            "wyposazenie",
        }
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in rows_by_key[next(iter(rows_by_key))].keys()
            if col not in exclude_keys
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_open_sports_fields_natural",
            set_=update_cols,
        )
        session.execute(stmt)

    return len(rows_by_key)


def _extract_event_geo(
    item: dict[str, Any],
) -> tuple[Optional[str], Optional[float], Optional[float]]:
    """Extract district, lat, lon from city event map/localization fields."""
    district: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    map_data = item.get("map")
    if isinstance(map_data, dict):
        features = map_data.get("features")
        if isinstance(features, list) and features:
            first_feat = features[0]
            if isinstance(first_feat, dict):
                lon, lat = _extract_lon_lat(first_feat.get("geometry"))
                props = first_feat.get("properties")
                if isinstance(props, dict):
                    district = _to_str(props.get("district"))

    if not district:
        loc = item.get("localization")
        if isinstance(loc, list) and loc and isinstance(loc[0], dict):
            district = _to_str(loc[0].get("name"))

    return district, lat, lon


def ingest_city_events(session: Session, records: list[dict[str, Any]]) -> int:
    """Upsert city calendar events by URL."""
    now = utc_now()
    rows_by_url: dict[str, dict[str, Any]] = {}

    for item in records:
        url = _to_str(item.get("url"))
        title = _to_str(item.get("title"))
        if not url or not title:
            continue
        district, lat, lon = _extract_event_geo(item)
        occurrences = item.get("occurrence", item.get("occurence"))
        rows_by_url[url] = {
            "url": url,
            "title": title,
            "lead": _to_str(item.get("lead")),
            "text": _to_str(item.get("text")),
            "language": _to_str(item.get("language")),
            "district": district,
            "lat": lat,
            "lon": lon,
            "category": (
                item.get("category")
                if isinstance(item.get("category"), list)
                else None
            ),
            "localization": (
                item.get("localization")
                if isinstance(item.get("localization"), list)
                else None
            ),
            "address": (
                item.get("address")
                if isinstance(item.get("address"), list)
                else None
            ),
            "map_data": (
                item.get("map") if isinstance(item.get("map"), dict) else None
            ),
            "occurrences": (
                occurrences if isinstance(occurrences, list) else None
            ),
            "image": (
                item.get("image")
                if isinstance(item.get("image"), dict)
                else None
            ),
            "updated_at": now,
        }

    if rows_by_url:
        stmt = pg_insert(CityEvent).values(list(rows_by_url.values()))
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in rows_by_url[next(iter(rows_by_url))].keys()
            if col != "url"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["url"],
            set_=update_cols,
        )
        session.execute(stmt)

    return len(rows_by_url)


def ingest_air_quality(session: Session, records: list[dict[str, Any]]) -> int:
    """Upsert air quality stations and append historical measurements."""
    now = utc_now()
    stations_by_name: dict[str, dict[str, Any]] = {}
    measurements_by_key: dict[tuple[str, str, datetime], dict[str, Any]] = {}

    for item in records:
        name = _to_str(item.get("name", item.get("Name")))
        if not name:
            continue
        addr = item.get("address", item.get("adres"))
        addr_dict = addr if isinstance(addr, dict) else {}
        ijp = item.get("ijp")
        ijp_dict = ijp if isinstance(ijp, dict) else {}

        stations_by_name[name] = {
            "name": name,
            "station": _to_str(item.get("station")),
            "station_type": _to_str(item.get("station_type")),
            "owner": _to_str(item.get("owner")),
            "data_source": _to_str(item.get("data_source")),
            "lat": _to_float(item.get("lat")),
            "lon": _to_float(item.get("lon")),
            "city": _to_str(addr_dict.get("city")),
            "commune": _to_str(addr_dict.get("commune")),
            "district": _to_str(addr_dict.get("district")),
            "street": _to_str(addr_dict.get("street")),
            "zip_code": _to_str(addr_dict.get("zip_code")),
            "current_ijp_name": _to_str(ijp_dict.get("name")),
            "current_ijp_recommendations": _to_str(
                ijp_dict.get("recommendations")
            ),
            "updated_at": now,
        }

        raw_data = item.get("data", item.get("pomiary"))
        if not isinstance(raw_data, list):
            continue
        for m in raw_data:
            if not isinstance(m, dict):
                continue
            p_code = _to_str(m.get("param_code"))
            m_time = _parse_dt(m.get("time"))
            if not p_code or m_time is None:
                continue
            m_ijp = m.get("ijp", m.get("index"))
            m_ijp_name = (
                _to_str(m_ijp.get("name")) if isinstance(m_ijp, dict) else None
            )
            measurements_by_key[(name, p_code, m_time)] = {
                "station_name": name,
                "param_code": p_code,
                "param_name": _to_str(m.get("param_name")),
                "measurement_time": m_time,
                "value": _to_float(m.get("value")),
                "unit": _to_str(m.get("unit")),
                "ijp_name": m_ijp_name,
                "fetched_at": now,
            }

    if stations_by_name:
        stmt = pg_insert(AirQualityStation).values(
            list(stations_by_name.values())
        )
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in stations_by_name[next(iter(stations_by_name))].keys()
            if col != "name"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_=update_cols,
        )
        session.execute(stmt)

    if measurements_by_key:
        m_stmt = pg_insert(AirQualityMeasurement).values(
            list(measurements_by_key.values())
        )
        m_stmt = m_stmt.on_conflict_do_nothing(
            constraint="uq_air_quality_station_param_time"
        )
        session.execute(m_stmt)

    return len(stations_by_name)


def ingest_streets_gl_venues(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert OpenStreetMap event venues into streets_gl_venues."""
    now = utc_now()
    rows_by_id: dict[str, dict[str, Any]] = {}

    for item in records:
        osm_id = _to_str(item.get("id"))
        if not osm_id:
            continue
        raw_tags = item.get("tags")
        tags = raw_tags if isinstance(raw_tags, dict) else {}
        rows_by_id[osm_id] = {
            "id": osm_id[:64],
            "name": ((_to_str(item.get("name")) or "")[:500] or None),
            "category": ((_to_str(item.get("category")) or "")[:120] or None),
            "location": ((_to_str(item.get("location")) or "")[:500] or None),
            "street": ((_to_str(item.get("street")) or "")[:255] or None),
            "housenumber": (
                (_to_str(item.get("housenumber")) or "")[:64] or None
            ),
            "postcode": ((_to_str(item.get("postcode")) or "")[:32] or None),
            "city": ((_to_str(item.get("city")) or "")[:120] or None),
            "lat": _to_float(item.get("lat")),
            "lon": _to_float(item.get("lon")),
            "opening_hours": _to_str(item.get("opening_hours")),
            "website": _to_str(item.get("website")),
            "phone": ((_to_str(item.get("phone")) or "")[:120] or None),
            "email": ((_to_str(item.get("email")) or "")[:255] or None),
            "wheelchair": (
                (_to_str(item.get("wheelchair")) or "")[:64] or None
            ),
            "capacity": ((_to_str(item.get("capacity")) or "")[:64] or None),
            "osm_url": _to_str(item.get("osm_url")),
            "streets_gl_url": _to_str(item.get("streets_gl_url")),
            "tags": tags,
            "updated_at": now,
        }

    all_rows = list(rows_by_id.values())
    batch_size = 500
    for idx in range(0, len(all_rows), batch_size):
        chunk = all_rows[idx: idx + batch_size]
        stmt = pg_insert(StreetsGlVenue).values(chunk)
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in chunk[0].keys()
            if col != "id"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_=update_cols,
        )
        session.execute(stmt)

    return len(all_rows)


def ingest_restaurants(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert OpenStreetMap restaurants and food/drink venues."""
    now = utc_now()
    rows_by_id: dict[str, dict[str, Any]] = {}

    for item in records:
        osm_id = _to_str(item.get("id"))
        name = _to_str(item.get("name"))
        if not osm_id or not name:
            continue
        raw_tags = item.get("tags")
        tags = raw_tags if isinstance(raw_tags, dict) else {}
        rows_by_id[osm_id] = {
            "id": osm_id[:64],
            "name": name[:500],
            "amenity": ((_to_str(item.get("amenity")) or "")[:64] or None),
            "cuisine": ((_to_str(item.get("cuisine")) or "")[:255] or None),
            "location": ((_to_str(item.get("location")) or "")[:500] or None),
            "street": ((_to_str(item.get("street")) or "")[:255] or None),
            "housenumber": (
                (_to_str(item.get("housenumber")) or "")[:64] or None
            ),
            "postcode": ((_to_str(item.get("postcode")) or "")[:32] or None),
            "city": ((_to_str(item.get("city")) or "")[:120] or None),
            "lat": _to_float(item.get("lat")),
            "lon": _to_float(item.get("lon")),
            "opening_hours": _to_str(item.get("opening_hours")),
            "website": _to_str(item.get("website")),
            "phone": ((_to_str(item.get("phone")) or "")[:120] or None),
            "email": ((_to_str(item.get("email")) or "")[:255] or None),
            "outdoor_seating": (
                (_to_str(item.get("outdoor_seating")) or "")[:64] or None
            ),
            "diet_vegan": (
                (_to_str(item.get("diet_vegan")) or "")[:64] or None
            ),
            "diet_vegetarian": (
                (_to_str(item.get("diet_vegetarian")) or "")[:64] or None
            ),
            "wheelchair": (
                (_to_str(item.get("wheelchair")) or "")[:64] or None
            ),
            "osm_url": _to_str(item.get("osm_url")),
            "tags": tags,
            "updated_at": now,
        }

    all_rows = list(rows_by_id.values())
    batch_size = 500
    for idx in range(0, len(all_rows), batch_size):
        chunk = all_rows[idx: idx + batch_size]
        stmt = pg_insert(Restaurant).values(chunk)
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in chunk[0].keys()
            if col != "id"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_=update_cols,
        )
        session.execute(stmt)

    return len(all_rows)


def ingest_entertainment_events(
    session: Session, records: list[dict[str, Any]]
) -> int:
    """Upsert Warsaw concerts and entertainment events."""
    now = utc_now()
    rows_by_id: dict[str, dict[str, Any]] = {}
    seen_urls: set[str] = set()

    for item in records:
        ext_id = _to_str(item.get("id"))
        source = _to_str(item.get("source")) or "external"
        title = _to_str(item.get("title"))
        url = _to_str(item.get("url"))
        if not ext_id or not title or not url:
            continue
        if url in seen_urls and ext_id not in rows_by_id:
            continue
        seen_urls.add(url)

        raw_performers = item.get("performers")
        performers = (
            raw_performers if isinstance(raw_performers, list) else []
        )
        raw_payload = item.get("raw_data")
        raw_data = raw_payload if isinstance(raw_payload, dict) else {}

        rows_by_id[ext_id] = {
            "id": ext_id[:128],
            "source": source[:64],
            "title": title[:500],
            "category": ((_to_str(item.get("category")) or "")[:120] or None),
            "start_date": (
                (_to_str(item.get("start_date")) or "")[:64] or None
            ),
            "end_date": ((_to_str(item.get("end_date")) or "")[:64] or None),
            "venue_name": (
                (_to_str(item.get("venue_name")) or "")[:255] or None
            ),
            "address": ((_to_str(item.get("address")) or "")[:500] or None),
            "district": ((_to_str(item.get("district")) or "")[:120] or None),
            "city": ((_to_str(item.get("city")) or "")[:120] or None),
            "lat": _to_float(item.get("lat")),
            "lon": _to_float(item.get("lon")),
            "url": url,
            "image_url": _to_str(item.get("image_url")),
            "description": _to_str(item.get("description")),
            "performers": performers,
            "is_free": ((_to_str(item.get("is_free")) or "")[:16] or None),
            "raw_data": raw_data,
            "updated_at": now,
        }

    all_rows = list(rows_by_id.values())
    batch_size = 500
    for idx in range(0, len(all_rows), batch_size):
        chunk = all_rows[idx: idx + batch_size]
        stmt = pg_insert(EntertainmentEvent).values(chunk)
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in chunk[0].keys()
            if col != "id"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_=update_cols,
        )
        session.execute(stmt)

    return len(all_rows)


INGEST_HANDLERS: dict[str, Callable[[Session, list[dict[str, Any]]], int]] = {
    "tourist_routes": ingest_tourist_routes,
    "toilets": ingest_toilets,
    "weather": ingest_weather,
    "defibrillators": ingest_defibrillators,
    "sports_activities": ingest_sports_activities,
    "open_sports_fields": ingest_open_sports_fields,
    "city_events": ingest_city_events,
    "air_quality": ingest_air_quality,
    "streets_gl": ingest_streets_gl_venues,
    "restaurants": ingest_restaurants,
    "entertainment_events": ingest_entertainment_events,
}


class DatabaseIngestor:
    """Orchestrates fetching Warsaw Open Data and persisting to PostgreSQL."""

    def __init__(
        self,
        engine: Engine,
        api_client: Optional[WarszawaApiClient] = None,
    ) -> None:
        self.engine = engine
        self.api_client = api_client or WarszawaApiClient()
        self._schema_initialized: bool = False

    def init_schema(self) -> None:
        """Create missing tables in current_schema() only."""
        with self.engine.begin() as conn:
            existing = set(
                conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = current_schema()"
                    )
                ).scalars()
            )
            for table in Base.metadata.sorted_tables:
                if table.name not in existing:
                    table.create(conn, checkfirst=False)
        self._schema_initialized = True

    def sync_spec(self, spec: DatasetSpec) -> int:
        """Fetch and ingest a single DatasetSpec, recording a SyncLog entry."""
        if not self._schema_initialized:
            self.init_schema()
        started = utc_now()
        handler = INGEST_HANDLERS.get(spec.key)
        if handler is None:
            raise KeyError(f"No ingest handler for dataset key: {spec.key}")

        with Session(self.engine) as session:
            try:
                records = self.api_client.fetch_spec(spec)
                count = handler(session, records)
                log_entry = SyncLog(
                    dataset_name=spec.key,
                    status="SUCCESS",
                    records_processed=count,
                    started_at=started,
                    finished_at=utc_now(),
                )
                session.add(log_entry)
                session.commit()
                return count
            except Exception as exc:
                session.rollback()
                err_log = SyncLog(
                    dataset_name=spec.key,
                    status="ERROR",
                    records_processed=0,
                    started_at=started,
                    finished_at=utc_now(),
                    error_message=str(exc),
                )
                session.add(err_log)
                session.commit()
                raise

    def sync_all_from_dane(self) -> dict[str, int]:
        """Synchronize all datasets listed in dane.txt."""
        self.init_schema()
        specs = parse_dane_file()
        summary: dict[str, int] = {}
        for spec in specs:
            summary[spec.key] = self.sync_spec(spec)
        return summary
