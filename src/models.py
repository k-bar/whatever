"""SQLAlchemy 2.0 ORM models for Warsaw Open Data PostgreSQL database."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


class TouristRoute(Base):
    """Tourist route in Warsaw (get_sbt_trasy_turystyczne)."""

    __tablename__ = "tourist_routes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    title: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    length_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traces: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    tourist_points: Mapped[Optional[list[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TouristPoint(Base):
    """Individual point of interest along tourist routes."""

    __tablename__ = "tourist_points"

    id_point: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Toilet(Base):
    """Public toilet location in Warsaw (get_m_toalety)."""

    __tablename__ = "toilets"
    __table_args__ = (
        UniqueConstraint(
            "lokalizacja", "lon", "lat", name="uq_toilets_loc_coords"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    zarzadca: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    typ: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lokalizacja: Mapped[str] = mapped_column(String(500), nullable=False)
    dzielnica: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    dostepnosc: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    platnosc: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    przewijak: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aktu_dan: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    poch_dan: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    godziny: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uwagi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class WeatherMeasurement(Base):
    """Weather station measurement history (get_zom_pogoda)."""

    __tablename__ = "weather_measurements"
    __table_args__ = (
        UniqueConstraint(
            "lokalizacja", "czas", name="uq_weather_station_time"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    lokalizacja: Mapped[str] = mapped_column(String(255), nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    czas: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
    temp_pow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temp_naw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wilg_pow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pred_wiatru: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kier_wiatru: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    int_opadu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Defibrillator(Base):
    """AED defibrillator location (get_scb_lokalizacja_defibrylatorow)."""

    __tablename__ = "defibrillators"

    defibrillator_id: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    device_access_description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    device_availability: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    device_location: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    device_manufacturer: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    device_public_access: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    device_specifications: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    location_building: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    location_city: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    location_description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    location_object_name: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    location_postcode: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    location_street: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SportsActivity(Base):
    """Sports activity from city calendar (get_bmm_zajecia_sportowe)."""

    __tablename__ = "sports_activities"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    time: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    category: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    day: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    dedicated: Mapped[Optional[list[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    localization: Mapped[Optional[list[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    address: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    image: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OpenSportsField(Base):
    """Open school sports facility (get_be_otwarte_boiska)."""

    __tablename__ = "open_sports_fields"
    __table_args__ = (
        UniqueConstraint(
            "nazwa_placowki",
            "adres_obiektu",
            "typ_obiektu",
            "wyposazenie",
            name="uq_open_sports_fields_natural",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    dzielnica: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    adres_obiektu: Mapped[str] = mapped_column(String(255), nullable=False)
    nazwa_placowki: Mapped[str] = mapped_column(String(500), nullable=False)
    typ_obiektu: Mapped[str] = mapped_column(String(255), nullable=False)
    wyposazenie: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rodzaj_nawierzchni: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    trybuny: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pilkochwyty: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    poniedzialek: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    wtorek: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sroda: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    czwartek: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    piatek: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sobota: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    niedziela: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    uwagi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_aktualizacji: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CityEvent(Base):
    """City cultural/social event (get_bmm_kalendarz_wydarzen)."""

    __tablename__ = "city_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    lead: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    localization: Mapped[Optional[list[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    address: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    map_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    occurrences: Mapped[Optional[list[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    image: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AirQualityStation(Base):
    """Air quality monitoring station (get_bopipk_monitoring_...)."""

    __tablename__ = "air_quality_stations"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    station: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    station_type: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data_source: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    commune: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    current_ijp_name: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    current_ijp_recommendations: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AirQualityMeasurement(Base):
    """Historical air quality parameter measurement per station."""

    __tablename__ = "air_quality_measurements"
    __table_args__ = (
        UniqueConstraint(
            "station_name",
            "param_code",
            "measurement_time",
            name="uq_air_quality_station_param_time",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    station_name: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("air_quality_stations.name", ondelete="CASCADE"),
        nullable=False,
    )
    param_code: Mapped[str] = mapped_column(String(64), nullable=False)
    param_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    measurement_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ijp_name: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class SyncLog(Base):
    """Audit log of dataset synchronization runs."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    dataset_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    records_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class StreetsGlVenue(Base):
    """Event venue in Warsaw from OpenStreetMap (used by streets.gl)."""

    __tablename__ = "streets_gl_venues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, index=True
    )
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    housenumber: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    postcode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opening_hours: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wheelchair: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    capacity: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    osm_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    streets_gl_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
