from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import create_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import Event, User
from app.schemas import FavouritesIO, LoginIn, Me, ProfileIn, PublicUser, RegisterIn, TokenOut

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
