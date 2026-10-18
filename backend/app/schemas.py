import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, HttpUrl, TypeAdapter

from app.categories import CATEGORIES
from app.config import settings

CategorySlug = Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users -----------------------------------------------------------------------------


Password = Annotated[str, Field(min_length=8, max_length=128)]


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    display_name: str = Field(min_length=1, max_length=80)
    username: str | None = Field(None, max_length=31)  # optional; made from display_name when missing


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class VerifyIn(BaseModel):
    token: str = Field(max_length=1000)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(max_length=1000)
    password: Password


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: Password


class EmailChangeIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class AccountDeleteIn(BaseModel):
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


_UPLOADED_PHOTO = re.compile(r"^/userevents/photos/[0-9a-f]{32}$")
_HTTP_URL = TypeAdapter(HttpUrl)


def _photo_ref(value: str) -> str:
    """A web address, or a photo uploaded through POST /userevents/photos (the profile picture)."""
    if not _UPLOADED_PHOTO.match(value):
        _HTTP_URL.validate_python(value)
    return value


PhotoRef = Annotated[str, Field(max_length=2000), AfterValidator(_photo_ref)]


class Hangout(BaseModel):
    """'You can find me at': a venue from the map (place_id = events.id) or just a name."""

    name: str = Field(min_length=1, max_length=80)
    place_id: int | None = None


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=80)
    username: str | None = Field(None, max_length=31)  # checked in app/usernames.py; 409 when taken
    gender: Literal["f", "m", ""] | None = None  # "" clears it
    first_name: str | None = Field(None, max_length=40)  # null or "" clears these three
    last_name: str | None = Field(None, max_length=60)
    age: int | None = Field(None, ge=13, le=120)
    hangouts: list[Hangout] | None = Field(None, max_length=5)
    bio: str | None = Field(None, max_length=2000)
    photos: list[PhotoRef] | None = Field(None, max_length=10)  # photos[0] is the profile picture
    interests: list[CategorySlug] | None = None
    links: dict[str, HttpUrl] | None = None  # {"instagram": "https://...", "github": "..."}


class PublicUser(ORM):
    """What other people see. Never includes email."""

    id: int
    username: str
    display_name: str
    gender: str | None
    bio: str | None
    photos: list[str]
    interests: list[str]
    hangouts: list[Hangout]


class ContactUser(PublicUser):
    """Shown once a join request is accepted."""

    links: dict[str, str]


class Me(ContactUser):
    email: str
    email_verified: (
        bool  # false + verify_required: friends, creating events, join requests and chats are locked
    )
    verify_required: bool = Field(default_factory=lambda: settings.require_verified_email)
    first_name: str | None
    last_name: str | None
    age: int | None
    created_at: datetime
    favourite_ids: list[int]


# --- profiles & friends -----------------------------------------------------------------------


class ProfileStats(BaseModel):
    friends: int
    been_to: int  # attended event dates that are over
    hosted: int  # events this person created (not cancelled)


class ProfileOut(PublicUser):
    """A profile page. relation is from the viewer's side."""

    stats: ProfileStats
    relation: Literal["self", "friends", "request_sent", "request_received", "none"]
    can_see_events: bool  # yourself and your friends see the going / been to / hosting lists


class UsernameCheck(BaseModel):
    username: str
    available: bool
    reason: str | None = None


class FriendRequestIn(BaseModel):
    username: str = Field(min_length=1, max_length=31)


class FriendRequestOut(BaseModel):
    id: int
    direction: Literal["incoming", "outgoing"]
    status: Literal["pending", "accepted"]
    user: PublicUser  # the other person
    created_at: datetime


class FriendDecisionIn(BaseModel):
    status: Literal["accepted", "declined"]


class ProfileEvent(BaseModel):
    """One line in going / been to / hosting."""

    event_id: int | None  # events.id (map pin), when it has one
    occurrence_id: int | None
    user_event_id: int | None  # for events made with "+ Create event"
    title: str
    starts_at: datetime
    ends_at: datetime | None
    venue_name: str | None
    image_url: str | None
    category: str | None
    lat: float | None
    lng: float | None


class FavouritesIO(BaseModel):
    """IDs of favourited events/venues (events.id); PUT replaces the whole list."""

    ids: list[int] = Field(max_length=1000)


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
    # filled by GET /me/attending so the profile can list "going to" / "been to" without extra calls
    event_id: int | None = None
    title: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


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
