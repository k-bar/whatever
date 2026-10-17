import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import create_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import User
from app.schemas import GuestIn, LoginIn, Me, ProfileIn, PublicUser, RegisterIn, TokenOut

router = APIRouter(tags=["users"])


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        photos=[],
        interests=[],
        links={},
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "Email already registered")
    return TokenOut(access_token=create_token(user.id))


@router.post("/auth/guest", response_model=TokenOut, status_code=201)
def guest(body: GuestIn, db: Session = Depends(get_db)):
    """A device account for people who haven't signed up: the app keeps the token, e.g. to create events."""
    user = User(
        email=f"guest-{uuid.uuid4().hex}@guest.syrenka.me",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        display_name=body.display_name,
        photos=[],
        interests=[],
        links={},
    )
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=Me)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=Me)
def update_me(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True, mode="json")
    for field, value in data.items():
        if value is not None:
            setattr(user, field, value)
    db.commit()
    return user


@router.get("/users/{user_id}", response_model=PublicUser)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user
