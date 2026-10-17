from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import usernames
from app.auth import create_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import Event, User
from app.schemas import FavouritesIO, LoginIn, Me, ProfileIn, PublicUser, RegisterIn, TokenOut

router = APIRouter(tags=["users"])


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if body.username:
        username = usernames.normalize(body.username)
        if why := usernames.problem(username):
            raise HTTPException(422, why)
        if usernames.is_taken(db, username):
            raise HTTPException(409, "Username taken")
    else:
        username = usernames.suggest(db, body.display_name)
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        username=username,
        photos=[],
        interests=[],
        links={},
        hangouts=[],
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if usernames.is_taken(db, username):
            raise HTTPException(409, "Username taken")
        raise HTTPException(409, "Email already registered")
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
    if data.get("username") is not None:
        data["username"] = usernames.normalize(data["username"])
        if why := usernames.problem(data["username"]):
            raise HTTPException(422, why)
        if usernames.is_taken(db, data["username"], except_user_id=user.id):
            raise HTTPException(409, "Username taken")
    if data.get("gender") == "":
        user.gender = None
        del data["gender"]
    for field, value in data.items():
        if value is not None:
            setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError:  # someone took the username a moment ago
        db.rollback()
        raise HTTPException(409, "Username taken")
    return user


@router.get("/me/favourites", response_model=FavouritesIO)
def my_favourites(user: User = Depends(get_current_user)):
    return FavouritesIO(ids=user.favourite_ids or [])


@router.put("/me/favourites", response_model=FavouritesIO)
def set_favourites(body: FavouritesIO, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Replace my favourited events/venues. Unknown IDs are dropped; order kept, duplicates removed."""
    wanted = list(dict.fromkeys(body.ids))
    known = set(db.scalars(select(Event.id).where(Event.id.in_(wanted)))) if wanted else set()
    user.favourite_ids = [i for i in wanted if i in known]
    db.commit()
    return FavouritesIO(ids=user.favourite_ids)


@router.get("/users/{user_id}", response_model=PublicUser)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user
