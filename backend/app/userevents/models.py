from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models import Event, User


class UserEvent(Base):
    """One event created by a user. `event_id` points at its public copy (Syrenka Users source)."""

    __tablename__ = "user_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    host_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(32))
    audience: Mapped[str] = mapped_column(String(16))  # public / public_confirm / friends / invite
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    venue_name: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("user_event_photos.id", ondelete="SET NULL"))
    invited_user_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / cancelled
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    host: Mapped[User] = relationship()
    event: Mapped[Event | None] = relationship()


class UserEventPhoto(Base):
    """Uploaded event photo. Kept in Postgres so it survives redeploys of the API box."""

    __tablename__ = "user_event_photos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4 hex, unguessable
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content_type: Mapped[str] = mapped_column(String(32))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
