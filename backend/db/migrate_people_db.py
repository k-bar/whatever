"""Adds the fields the website's users API needs to the ludzie table in people.db.

The API (https://api.syrenka.me/docs, tag "users") works with:
    /auth/register, /auth/login   -> email, password, display_name
    /me (GET, PATCH)              -> id, display_name, bio, photos, interests, links, email, created_at
    /users/{user_id}              -> id, display_name, bio, photos, interests

ludzie already has id and email_address; this adds the rest. Safe to run more than once.

    python migrate_people_db.py
"""

import sqlite3
from pathlib import Path

PEOPLE_DB_PATH = Path(__file__).resolve().parent / "people.db"

# name -> column definition (ALTER TABLE ADD COLUMN needs constant defaults)
NEW_COLUMNS = {
    "password_hash": "TEXT",  # NULL = this person cannot log in yet
    "display_name": "TEXT CHECK (display_name IS NULL OR length(display_name) BETWEEN 1 AND 80)",
    "bio": "TEXT CHECK (bio IS NULL OR length(bio) <= 2000)",
    "photos": "TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(photos) AND json_type(photos) = 'array')",
    "interests": "TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(interests) AND json_type(interests) = 'array')",
    "links": "TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(links) AND json_type(links) = 'object')",
    "created_at": "TEXT",
}


def migrate(path=PEOPLE_DB_PATH):
    conn = sqlite3.connect(path)
    with conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(ludzie)")}
        for name, definition in NEW_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE ludzie ADD COLUMN {name} {definition}")
        # fill the new columns for people who were already there
        conn.execute("UPDATE ludzie SET display_name = first_name || ' ' || second_name WHERE display_name IS NULL")
        conn.execute("UPDATE ludzie SET photos = json_array(photo) WHERE photo IS NOT NULL AND photos = '[]'")
        conn.execute("UPDATE ludzie SET created_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE created_at IS NULL")
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS ludzie_created_at AFTER INSERT ON ludzie WHEN NEW.created_at IS NULL "
            "BEGIN UPDATE ludzie SET created_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id; END"
        )
    for row in conn.execute("SELECT id, email_address, display_name, photos, interests, links, created_at FROM ludzie"):
        print(" ", row)
    conn.close()


if __name__ == "__main__":
    migrate()
