"""'I'm going, come with me': attendance and join requests."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, get_verified_user
from app.db import get_db
from app.friends import friend_ids
from app.models import Attendance, Event, JoinRequest, Occurrence, User
from app.schemas import (
    AttendanceIn,
    AttendanceOut,
    AttendeeOut,
    ContactUser,
    JoinRequestDecision,
    JoinRequestIn,
    JoinRequestOut,
    PublicUser,
)

router = APIRouter(tags=["social"])


def get_occurrence(db: Session, occurrence_id: int) -> Occurrence:
    occ = db.scalar(
        select(Occurrence).where(Occurrence.id == occurrence_id).options(selectinload(Occurrence.event))
    )
    if occ is None:
        raise HTTPException(404, "Occurrence not found")
    return occ


@router.put("/occurrences/{occurrence_id}/attendance", response_model=AttendanceOut)
def set_attendance(
    occurrence_id: int,
    body: AttendanceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Say you're going. wants_company=true puts you in the 'come with me' list."""
    get_occurrence(db, occurrence_id)
    att = db.get(Attendance, (user.id, occurrence_id))
    if att is None:
        att = Attendance(user_id=user.id, occurrence_id=occurrence_id)
        db.add(att)
    att.wants_company = body.wants_company
    att.max_group = body.max_group
    db.commit()
    db.refresh(att)
    return att


@router.delete("/occurrences/{occurrence_id}/attendance", status_code=204)
def remove_attendance(
    occurrence_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    att = db.get(Attendance, (user.id, occurrence_id))
    if att is not None:
        db.delete(att)
        db.commit()
    return Response(status_code=204)


@router.get("/occurrences/{occurrence_id}/attendees", response_model=list[AttendeeOut])
def list_attendees(
    occurrence_id: int,
    wants_company: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Attendance)
        .where(Attendance.occurrence_id == occurrence_id)
        .options(selectinload(Attendance.user))
        .order_by(Attendance.created_at)
    )
    if wants_company is not None:
        stmt = stmt.where(Attendance.wants_company == wants_company)
    # Who goes where is friends-only on profiles, so it is here too: you see yourself, your friends, the
    # demo people, and anyone who said "come with me" (wants_company: that list is meant to be seen).
    mine = {user.id, *friend_ids(db, user.id)}
    return [a for a in db.scalars(stmt) if a.wants_company or a.user_id in mine or a.user.is_mock]


@router.get("/me/attending", response_model=list[AttendanceOut])
def my_attendance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Attendance)
        .where(Attendance.user_id == user.id)
        .options(selectinload(Attendance.occurrence).selectinload(Occurrence.event))
        .order_by(Attendance.created_at.desc())
    ).all()
    return [
        AttendanceOut.model_validate(a).model_copy(
            update={
                "event_id": a.occurrence.event_id,
                "title": a.occurrence.event.title,
                "starts_at": a.occurrence.starts_at,
                "ends_at": a.occurrence.ends_at,
            }
        )
        for a in rows
    ]


def join_request_out(jr: JoinRequest, viewer: User) -> JoinRequestOut:
    # contact links are revealed to both sides once the request is accepted
    show = ContactUser if jr.status == "accepted" else PublicUser
    return JoinRequestOut(
        id=jr.id,
        occurrence_id=jr.occurrence_id,
        event_id=jr.occurrence.event_id,
        event_title=jr.occurrence.event.title,
        starts_at=jr.occurrence.starts_at,
        status=jr.status,
        message=jr.message,
        created_at=jr.created_at,
        requester=show.model_validate(jr.requester),
        target=show.model_validate(jr.target),
    )


def load_request(db: Session, request_id: int) -> JoinRequest | None:
    return db.scalar(
        select(JoinRequest)
        .where(JoinRequest.id == request_id)
        .options(
            selectinload(JoinRequest.requester),
            selectinload(JoinRequest.target),
            selectinload(JoinRequest.occurrence).selectinload(Occurrence.event),
        )
    )


@router.post("/occurrences/{occurrence_id}/join-requests", response_model=JoinRequestOut, status_code=201)
def create_join_request(
    occurrence_id: int,
    body: JoinRequestIn,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Ask to join someone who is going and wants company (or the host of an invitation)."""
    occ = get_occurrence(db, occurrence_id)
    if body.target_user_id == user.id:
        raise HTTPException(422, "You can't send a request to yourself")
    target_att = db.get(Attendance, (body.target_user_id, occurrence_id))
    is_host = occ.event.host_user_id == body.target_user_id
    if not is_host and (target_att is None or not target_att.wants_company):
        raise HTTPException(409, "That person isn't looking for company for this event")
    jr = JoinRequest(
        occurrence_id=occurrence_id,
        target_user_id=body.target_user_id,
        requester_id=user.id,
        message=body.message,
    )
    db.add(jr)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "You already sent this person a request for this event")
    return join_request_out(load_request(db, jr.id), user)


@router.get("/me/join-requests", response_model=list[JoinRequestOut])
def my_join_requests(
    direction: Literal["incoming", "outgoing", "all"] = "incoming",
    status: Literal["pending", "accepted", "rejected"] | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Incoming + pending = the swipe deck, oldest first."""
    stmt = select(JoinRequest).options(
        selectinload(JoinRequest.requester),
        selectinload(JoinRequest.target),
        selectinload(JoinRequest.occurrence).selectinload(Occurrence.event),
    )
    if direction == "incoming":
        stmt = stmt.where(JoinRequest.target_user_id == user.id)
    elif direction == "outgoing":
        stmt = stmt.where(JoinRequest.requester_id == user.id)
    else:
        stmt = stmt.where(or_(JoinRequest.target_user_id == user.id, JoinRequest.requester_id == user.id))
    if status:
        stmt = stmt.where(JoinRequest.status == status)
    return [join_request_out(jr, user) for jr in db.scalars(stmt.order_by(JoinRequest.created_at)).all()]


@router.patch("/join-requests/{request_id}", response_model=JoinRequestOut)
def decide_join_request(
    request_id: int,
    body: JoinRequestDecision,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Swipe: accept or reject. Only the person who received the request can decide."""
    jr = load_request(db, request_id)
    if jr is None or jr.target_user_id != user.id:
        raise HTTPException(404, "Join request not found")
    if jr.status != "pending":
        raise HTTPException(409, f"Already {jr.status}")
    jr.status = body.status
    event: Event = jr.occurrence.event
    if body.status == "accepted" and event.seats_left is not None:
        # one atomic decrement: two hosts' taps at once can't both take the last seat
        took = db.execute(
            update(Event)
            .where(Event.id == event.id, Event.seats_left > 0)
            .values(seats_left=Event.seats_left - 1)
        )
        if took.rowcount == 0:
            db.rollback()
            raise HTTPException(409, "No seats left")
    db.commit()
    return join_request_out(load_request(db, request_id), user)
