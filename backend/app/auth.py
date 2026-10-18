"""Accounts: argon2 password hashes (pwdlib: salted, self-describing, upgraded on login) and JWTs.

Login tokens carry the user's token_version: bumping it (password change or reset, "log out
everywhere") ends every session at once. Mail links carry single-purpose tokens instead:
    verify   bound to the email address it was sent to; works until it expires
    reset    bound to the current password hash, so it stops working once the password changes
Social features (friends, creating events, join requests, chat) need a verified email:
get_verified_user.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

password_hash = PasswordHash.recommended()  # argon2id, random salt per hash
bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"
# Compared against when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = password_hash.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def check_password(user: User | None, password: str) -> bool:
    """Constant-ish time check; rehashes when pwdlib's recommended parameters changed (caller commits)."""
    if user is None:
        password_hash.verify(password, _DUMMY_HASH)
        return False
    ok, new_hash = password_hash.verify_and_update(password, user.password_hash)
    if ok and new_hash:
        user.password_hash = new_hash
    return ok


def create_token(user: User) -> str:
    exp = datetime.now(UTC) + timedelta(days=settings.jwt_expire_days)
    payload = {"sub": str(user.id), "ver": user.token_version, "exp": exp}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def create_mail_token(user: User, purpose: str) -> str:
    if purpose == "verify":
        ttl, bind = timedelta(hours=settings.verify_token_hours), user.email
    else:
        ttl, bind = timedelta(minutes=settings.reset_token_minutes), user.password_hash
    payload = {
        "sub": str(user.id),
        "purpose": purpose,
        "fp": _fingerprint(bind),
        "exp": datetime.now(UTC) + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def read_mail_token(db: Session, token: str, purpose: str) -> User:
    """The user a verify / reset link belongs to, or 400 when it's expired, used or tampered with."""
    bad = HTTPException(400, "This link is invalid or has expired")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise bad
    if payload.get("purpose") != purpose:
        raise bad
    user = db.get(User, int(payload["sub"]))
    bind = None if user is None else (user.email if purpose == "verify" else user.password_hash)
    if bind is None or payload.get("fp") != _fingerprint(bind):
        raise bad
    return user


def user_from_token(db: Session, token: str) -> User:
    """The user behind a login token (HTTP bearer or the chat WebSocket); 401 otherwise."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if "purpose" in payload:  # a mail link is not a login
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session ended, log in again")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User | None:
    if creds is None:
        return None
    return user_from_token(db, creds.credentials)


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return user


def get_verified_user(user: User = Depends(get_current_user)) -> User:
    if settings.require_verified_email and user.email_verified_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Confirm your email first")
    return user
