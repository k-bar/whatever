"""@usernames, Instagram style: 3-30 of a-z 0-9 . _ (no leading/trailing dot, no "..").

Stored lowercase, so "Ola.K" and "ola.k" are the same name. Users pick their own and may change it
while the new one is free; new accounts get one made from their display name.
"""

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User

PATTERN = re.compile(r"^(?!\.)(?!.*\.\.)(?!.*\.$)[a-z0-9._]{3,30}$")
RESERVED = {
    "admin",
    "administrator",
    "api",
    "app",
    "auth",
    "help",
    "login",
    "logout",
    "me",
    "mod",
    "moderator",
    "null",
    "official",
    "register",
    "root",
    "settings",
    "support",
    "syrenka",
    "syrenka.me",
    "system",
    "warszawa",
}
_POLISH = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def normalize(name: str) -> str:
    return name.strip().lstrip("@").lower()


def problem(name: str) -> str | None:
    """Why this username can't be used (format only), or None."""
    if not PATTERN.match(name):
        return "Use 3-30 letters, digits, dots or underscores (no dot at the start or end, no '..')"
    if name in RESERVED:
        return "That username is reserved"
    return None


def is_taken(db: Session, name: str, except_user_id: int | None = None) -> bool:
    stmt = select(func.count()).select_from(User).where(User.username == name)
    if except_user_id is not None:
        stmt = stmt.where(User.id != except_user_id)
    return db.scalar(stmt) > 0


def suggest(db: Session, display_name: str) -> str:
    """A free username made from a display name: "Łucja Kowalska" -> "lucja.kowalska" (or .2, .3, ...)."""
    plain = unicodedata.normalize("NFKD", display_name.translate(_POLISH)).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", ".", plain.lower()).strip(".")[:24] or "user"
    if len(base) < 3:
        base = f"{base}.user"
    if base in RESERVED:
        base = f"{base}.user"
    name, n = base, 1
    while is_taken(db, name):
        n += 1
        name = f"{base}.{n}"
    return name
