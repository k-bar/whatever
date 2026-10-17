from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.categories import CATEGORIES

CategorySlug = Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users -----------------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=80)
    bio: str | None = Field(None, max_length=2000)
    photos: list[HttpUrl] | None = Field(None, max_length=10)
    interests: list[CategorySlug] | None = None
    links: dict[str, HttpUrl] | None = None  # {"instagram": "https://...", "github": "..."}


class PublicUser(ORM):
    """What other people see. Never includes email."""

    id: int
    display_name: str
    bio: str | None
    photos: list[str]
    interests: list[str]


class ContactUser(PublicUser):
    """Shown once a join request is accepted."""

    links: dict[str, str]


class Me(ContactUser):
    email: str
    created_at: datetime


# --- events -----------------------------------------------------------------------------------


class Category(BaseModel):
    slug: str
    label: str


class SourceOut(ORM):
    slug: str
    name: str
    url: str | None
    is_reliable: bool
    last_run_at: datetime | None
    last_status: str | None
    item_count: int


class OccurrenceOut(ORM):
    id: int
    starts_at: datetime
    ends_at: datetime | None
    daily: bool
    attendees: int = 0
    wanting_company: int = 0


class EventOut(ORM):
    id: int
    kind: str
    title: str
    categories: list[str]
    lead: str | None
    text_plain: str | None
    text_html: str | None
    image_url: str | None
    url: str | None
    district: str | None
    venue_name: str | None
    address: str | None
    lat: float | None
    lng: float | None
    opening_hours: dict[str, str] | None
    contact: dict[str, str]
    audience: list[str]
    is_public_invite: bool
    capacity: int | None
    seats_left: int | None
    source: str
    host: PublicUser | None = None
    occurrences: list[OccurrenceOut] = []


class InviteIn(BaseModel):
    """A public invitation: picnic, concert, 'come to my place'..."""

    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(None, max_length=5000)
    categories: list[CategorySlug] = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime | None = None
    lat: float = Field(ge=52.09, le=52.37)
    lng: float = Field(ge=20.85, le=21.28)
    venue_name: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=300)
    image_url: HttpUrl | None = None
    capacity: int | None = Field(None, ge=1, le=1000)


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]


# --- social -----------------------------------------------------------------------------------


class AttendanceIn(BaseModel):
    wants_company: bool = False
    max_group: int | None = Field(None, ge=2, le=10)  # squads: "we're 3, looking for 1 more"


class AttendanceOut(ORM):
    occurrence_id: int
    wants_company: bool
    max_group: int | None
    created_at: datetime


class AttendeeOut(ORM):
    user: PublicUser
    wants_company: bool
    max_group: int | None


class JoinRequestIn(BaseModel):
    target_user_id: int
    message: str | None = Field(None, max_length=500)


class JoinRequestDecision(BaseModel):
    status: Literal["accepted", "rejected"]


class JoinRequestOut(ORM):
    id: int
    occurrence_id: int
    event_id: int
    event_title: str
    starts_at: datetime
    status: str
    message: str | None
    created_at: datetime
    requester: PublicUser | ContactUser
    target: PublicUser | ContactUser
