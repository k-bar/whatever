from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import mail, usernames
from app.auth import (
    check_password,
    create_mail_token,
    create_token,
    get_current_user,
    hash_password,
    read_mail_token,
)
from app.config import settings
from app.db import get_db
from app.models import Event, User
from app.schemas import (
    AccountDeleteIn,
    EmailChangeIn,
    FavouritesIO,
    ForgotPasswordIn,
    LoginIn,
    Me,
    PasswordChangeIn,
    ProfileIn,
    PublicUser,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    VerifyIn,
)

router = APIRouter(tags=["users"])


def by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def may_mail(user: User) -> bool:
    """At most one verification / reset mail per account per mail_resend_seconds (stamps it when true)."""
    now = datetime.now(UTC)
    if user.last_mail_at and now - user.last_mail_at < timedelta(seconds=settings.mail_resend_seconds):
        return False
    user.last_mail_at = now
    return True


def queue_verification(tasks: BackgroundTasks, user: User) -> None:
    link = f"{settings.web_url}/?verify={create_mail_token(user, 'verify')}"
    tasks.add_task(mail.send, mail.verification_mail(user.email, user.display_name, link))


def end_sessions(user: User) -> None:
    user.token_version += 1


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Create an account and mail a confirmation link. The new account can log in straight away;
    friends, creating events, join requests and chats wait until the email is confirmed."""
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
        last_mail_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if usernames.is_taken(db, username):
            raise HTTPException(409, "Username taken")
        raise HTTPException(409, "Email already registered")
    queue_verification(tasks, user)
    return TokenOut(access_token=create_token(user))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = by_email(db, body.email)
    now = datetime.now(UTC)
    if user is not None and user.locked_until and user.locked_until > now:
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            429, f"Too many wrong passwords. Try again in {minutes} min or reset your password"
        )
    if not check_password(user, body.password):
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.failed_logins, user.locked_until = (
                    0,
                    now + timedelta(minutes=settings.login_lock_minutes),
                )
            db.commit()
        raise HTTPException(401, "Wrong email or password")
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    return TokenOut(access_token=create_token(user))


@router.post("/auth/verify", response_model=Me)
def verify_email(body: VerifyIn, db: Session = Depends(get_db)):
    """The link from the confirmation mail (?verify=<token>). Works without being logged in."""
    user = read_mail_token(db, body.token, "verify")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        db.commit()
    return user


@router.post("/auth/verify/resend", status_code=202)
def resend_verification(
    tasks: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if user.email_verified_at is not None:
        raise HTTPException(409, "Your email is already confirmed")
    if not may_mail(user):
        raise HTTPException(429, "We just sent one. Check your inbox (and spam), or try again in a minute")
    db.commit()
    queue_verification(tasks, user)
    return {"sent_to": user.email}


@router.post("/auth/password/forgot", status_code=202)
def forgot_password(body: ForgotPasswordIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Mail a reset link. Answers the same whether or not the address has an account."""
    user = by_email(db, body.email)
    if user is not None and may_mail(user):
        db.commit()
        link = f"{settings.web_url}/?reset={create_mail_token(user, 'reset')}"
        tasks.add_task(mail.send, mail.reset_mail(user.email, user.display_name, link))
    return {"detail": "If that address has an account, a reset link is on its way"}


@router.post("/auth/password/reset", response_model=TokenOut)
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    """Set a new password from the mailed link. Ends every other session; returns a fresh login.
    The mail reached the inbox, so this also confirms the email."""
    user = read_mail_token(db, body.token, "reset")
    user.password_hash = hash_password(body.password)
    user.failed_logins, user.locked_until = 0, None
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    end_sessions(user)
    db.commit()
    return TokenOut(access_token=create_token(user))


@router.post("/me/password", response_model=TokenOut)
def change_password(
    body: PasswordChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Change the password (needs the current one). Logs out every other device."""
    if not check_password(user, body.current_password):
        raise HTTPException(403, "Current password is wrong")
    user.password_hash = hash_password(body.new_password)
    end_sessions(user)
    db.commit()
    return TokenOut(access_token=create_token(user))


@router.post("/me/email", response_model=Me)
def change_email(
    body: EmailChangeIn,
    tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Move the account to another address (needs the password). The new one has to be confirmed."""
    if not check_password(user, body.password):
        raise HTTPException(403, "Password is wrong")
    email = body.email.lower()
    if email == user.email:
        return user
    if by_email(db, email) is not None:
        raise HTTPException(409, "Email already registered")
    user.email, user.email_verified_at, user.last_mail_at = email, None, datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    queue_verification(tasks, user)
    return user


@router.post("/auth/logout-all", response_model=TokenOut)
def logout_everywhere(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """End every session (all devices). Returns a new login for this one."""
    end_sessions(user)
    db.commit()
    return TokenOut(access_token=create_token(user))


@router.delete("/me", status_code=204)
def delete_account(
    body: AccountDeleteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete the account for good (needs the password). Events I host leave the map like a cancel;
    everything else that is mine (profile, friends, attendance, my events, photos, chat messages)
    goes with the user row through ON DELETE CASCADE."""
    if not check_password(user, body.password):
        raise HTTPException(403, "Password is wrong")
    for event in db.scalars(select(Event).where(Event.host_user_id == user.id)):
        if event.is_active:
            event.is_active = False
            event.source.item_count = max(0, (event.source.item_count or 1) - 1)
        event.host_user_id = None
    db.flush()  # no ORM relationship orders these before the DELETE
    db.delete(user)
    db.commit()
    return Response(status_code=204)


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
    for field in ("first_name", "last_name"):
        if field in data:
            data[field] = (data[field] or "").strip() or None
    for field, value in data.items():
        # bio and the personal details: null clears them; other fields can't be emptied to null
        if value is not None or field in ("bio", "first_name", "last_name", "age"):
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
