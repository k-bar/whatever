"""The friends graph (table friendships), shared by profiles, user events and chats."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Friendship


def pair(db: Session, a: int, b: int) -> Friendship | None:
    return db.scalar(
        select(Friendship).where(
            func.least(Friendship.requester_id, Friendship.addressee_id) == min(a, b),
            func.greatest(Friendship.requester_id, Friendship.addressee_id) == max(a, b),
        )
    )


def friend_ids(db: Session, user_id: int) -> list[int]:
    rows = db.execute(
        select(Friendship.requester_id, Friendship.addressee_id).where(
            Friendship.status == "accepted",
            or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
        )
    ).all()
    return [b if a == user_id else a for a, b in rows]


def are_friends(db: Session, a: int, b: int) -> bool:
    f = pair(db, a, b)
    return f is not None and f.status == "accepted"
