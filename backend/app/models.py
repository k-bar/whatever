from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    is_reliable: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(16))  # ok / error
    last_error: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source_id", "external_key"),
        Index("ix_events_location", "location", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_key: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(16), default="event")  # event / class / place
    title: Mapped[str] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    categories_raw: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    lead: Mapped[str | None] = mapped_column(Text)
    text_plain: Mapped[str | None] = mapped_column(Text)
    text_html: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    district: Mapped[str | None] = mapped_column(String(64))
    venue_name: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSONB)
    contact: Mapped[dict] = mapped_column(JSONB, default=dict)
    audience: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    # title + lead in Polish and English, made offline (app/translate.py):
    # {"orig": "pl", "for": "<title>\n<lead>", "pl": {"title", "lead"}, "en": {"title", "lead"}}
    i18n: Mapped[dict | None] = mapped_column(JSONB)
    host_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_public_invite: Mapped[bool] = mapped_column(Boolean, default=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    seats_left: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[Source] = relationship()
    occurrences: Mapped[list["Occurrence"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="Occurrence.starts_at"
    )


class Occurrence(Base):
    __tablename__ = "event_occurrences"
    __table_args__ = (UniqueConstraint("event_id", "starts_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    daily: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[Event] = relationship(back_populates="occurrences")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(80))
    # @username, Instagram style: unique, lowercase, chosen by the user (app/usernames.py)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    gender: Mapped[str | None] = mapped_column(String(1))  # f / m / null; Polish labels: Byłam / Byłem
    # Personal details: only the user sees them (Me), never in public profiles
    first_name: Mapped[str | None] = mapped_column(String(40))
    last_name: Mapped[str | None] = mapped_column(String(60))
    age: Mapped[int | None] = mapped_column(SmallInteger)
    # "You can find me at": [{"name": "Spatif", "place_id": 123 | null}], up to 5
    hangouts: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    bio: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    interests: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    links: Mapped[dict] = mapped_column(JSONB, default=dict)
    # IDs of favourited events/venues (events.id), saved with the account so stars follow you between devices
    favourite_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attendance(Base):
    __tablename__ = "attendance"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("event_occurrences.id", ondelete="CASCADE"), primary_key=True
    )
    wants_company: Mapped[bool] = mapped_column(Boolean, default=False)
    max_group: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    occurrence: Mapped[Occurrence] = relationship()


class JoinRequest(Base):
    __tablename__ = "join_requests"
    __table_args__ = (UniqueConstraint("occurrence_id", "target_user_id", "requester_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("event_occurrences.id", ondelete="CASCADE"))
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / accepted / rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    target: Mapped[User] = relationship(foreign_keys=[target_user_id])
    occurrence: Mapped[Occurrence] = relationship()


class Friendship(Base):
    """A friend request; accepted = friends. One row per pair of people, whoever asked first."""

    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("requester_id <> addressee_id", name="ck_friendships_not_self"),
        Index(
            "ux_friendships_pair",
            text("least(requester_id, addressee_id)"),
            text("greatest(requester_id, addressee_id)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / accepted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    addressee: Mapped[User] = relationship(foreign_keys=[addressee_id])


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    lat: Mapped[float | None] = mapped_column(Float)  # null = looked up, not found
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TextTranslation(Base):
    """Polish and English versions of one exact text, so repeated titles are translated once."""

    __tablename__ = "text_translations"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the text
    orig: Mapped[str] = mapped_column(String(8))  # detected language of the text: pl / en / ...
    pl: Mapped[str] = mapped_column(Text)
    en: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- live conditions and routes (Warsaw Open Data, app/ingest/conditions.py and routes.py) ----


class WeatherStation(Base):
    """Road weather stations: latest reading only, refreshed every 10 minutes."""

    __tablename__ = "weather_stations"

    name: Mapped[str] = mapped_column(String(120), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    temp_air: Mapped[float | None] = mapped_column(Float)  # °C
    temp_road: Mapped[float | None] = mapped_column(Float)  # °C, road surface
    humidity: Mapped[float | None] = mapped_column(Float)  # %
    wind_speed: Mapped[float | None] = mapped_column(Float)  # m/s
    wind_dir: Mapped[int | None] = mapped_column(Integer)  # degrees
    precipitation: Mapped[float | None] = mapped_column(Float)  # intensity as reported
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AirStation(Base):
    """Air quality stations: latest value per parameter, refreshed every 10 minutes."""

    __tablename__ = "air_stations"

    name: Mapped[str] = mapped_column(String(120), primary_key=True)
    station: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(64))
    street: Mapped[str | None] = mapped_column(Text)
    index_name: Mapped[str | None] = mapped_column(String(32))  # Polish air quality index, e.g. "Dobry"
    recommendation: Mapped[str | None] = mapped_column(Text)
    # {"PM10": {"name", "value", "unit", "index", "time"}, ...}
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TouristRoute(Base):
    """Kamil's table (src/models.py): raw API shape. /routes builds the LineString from traces."""

    __tablename__ = "tourist_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), unique=True)
    length_km: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    traces: Mapped[list | None] = mapped_column(JSONB)  # [[lat, lng], ...] as the API sends it
    tourist_points: Mapped[list | None] = mapped_column(JSONB)  # [{"id_point", "name", "latlng": {...}}]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
