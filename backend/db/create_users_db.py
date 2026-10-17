"""Creates the user profiles database (users.db).

Only `email` and `username` are required; every other profile field is optional.
`username` is an Instagram-style @handle: lowercase letters, digits, "." and "_",
up to 30 characters, unique, chosen by the user and changeable while the new
handle is free (old handles are kept in `username_history`).

The photo lives only in `people` (one row per person, keyed by id and username),
stored as a BLOB with its MIME type; only real image files (JPEG, PNG, WebP, GIF)
are accepted - the format is checked from the file's bytes, not its name.

Tables:
    users                 account and profile data
    username_history      previous @handles
    favourite_locations   saved places (venues from street_gl.db or custom ones)
    user_events           events from other databases the user is going to / has been to
    hosted_events         events the user is hosting (public invitations)
    people                one row per person: username, about me, hobby, events, photo
    friendships           friend requests and friends; views `friends`, `friend_requests`
    user_profiles         (view) whole profile in one row, with photo and JSON lists

Usage:
    python create_users_db.py                  # create empty tables (safe to re-run)
    python create_users_db.py --demo           # also add mock users and their data
    python create_users_db.py --reset --demo   # drop all tables and start again
    python create_users_db.py --photo anna.kowalska path/to/photo.jpg
    python create_users_db.py --rename anna.kowalska ania.k

Every run also writes people.db: the people table on its own.
"""

import argparse
import json
import random
import re
import sqlite3
import struct
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "users.db"
PEOPLE_DB_PATH = HERE / "people.db"  # copy of the people table alone
KUP_BILECIK_DB = HERE / "kup_bilecik.db"
EVENTS_DB = HERE / "events.db"
STREET_GL_DB = HERE / "street_gl.db"

# Event categories from docs/PLAN.md, used for `interests` and hosted events
CATEGORIES = [
    "music", "nightlife", "theatre", "film", "exhibitions", "meetups", "grzybki",
    "study_buddies", "running", "yoga", "sports", "festivals", "markets", "culture",
]

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
MAX_PHOTO_BYTES = 5 * 1024 * 1024
USERNAME_RE = re.compile(r"^(?!\.)(?!.*\.\.)(?!.*\.$)[a-z0-9._]{1,30}$")

# people.name, first_name, second_name, email, wiek, plec computed from a users row (NEW) inside triggers
PERSON_FIELDS = """
        nullif(trim(coalesce(NEW.first_name, '') || ' ' || coalesce(NEW.last_name, '')), ''),
        NEW.first_name,
        NEW.last_name,
        NEW.email,
        CAST(strftime('%Y', 'now') AS INTEGER) - CAST(strftime('%Y', NEW.birth_date) AS INTEGER)
            - (strftime('%m-%d', 'now') < strftime('%m-%d', NEW.birth_date)),
        CASE NEW.gender WHEN 'male' THEN 'mężczyzna' WHEN 'female' THEN 'kobieta' END"""

SCHEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    email            TEXT NOT NULL UNIQUE COLLATE NOCASE
                     CHECK (email LIKE '%_@_%._%'),
    username         TEXT NOT NULL UNIQUE           -- @handle without the "@"
                     CHECK (length(username) BETWEEN 1 AND 30
                            AND username = lower(username)
                            AND username NOT GLOB '*[^a-z0-9._]*'
                            AND username NOT LIKE '.%' AND username NOT LIKE '%.'
                            AND instr(username, '..') = 0),
    -- everything below is optional
    first_name       TEXT,
    last_name        TEXT,                -- second name / surname
    display_name     TEXT,
    password_hash    TEXT,                -- set by the backend, never plain text
    birth_date       TEXT                 -- YYYY-MM-DD
                     CHECK (birth_date IS NULL OR date(birth_date) IS birth_date),
    gender           TEXT,
    pronouns         TEXT,
    bio              TEXT,
    hobbies          TEXT,                -- JSON list, e.g. ["szachy", "wspinaczka"]
    interests        TEXT,                -- JSON list of event categories (CATEGORIES)
    languages        TEXT,                -- JSON list, e.g. ["pl", "en"]
    nationality      TEXT,
    occupation       TEXT,
    university       TEXT,
    city             TEXT DEFAULT 'Warszawa',
    district         TEXT,                -- Mokotów, Wola, ...
    new_in_city      INTEGER CHECK (new_in_city IN (0, 1)),  -- expat / student / moved recently
    phone            TEXT,
    instagram        TEXT,
    facebook         TEXT,
    github           TEXT,
    linkedin         TEXT,
    tiktok           TEXT,
    spotify          TEXT,
    website          TEXT,
    looking_for      TEXT,                -- e.g. "towarzystwo na koncerty"
    preferred_squad_size INTEGER CHECK (preferred_squad_size IS NULL OR preferred_squad_size BETWEEN 1 AND 20),
    is_public        INTEGER NOT NULL DEFAULT 1 CHECK (is_public IN (0, 1)),
    is_verified      INTEGER NOT NULL DEFAULT 0 CHECK (is_verified IN (0, 1)),
    last_seen_at     TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS username_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    old_username TEXT NOT NULL,
    new_username TEXT NOT NULL,
    changed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS favourite_locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source      TEXT NOT NULL DEFAULT 'custom'
                CHECK (source IN ('street_gl', 'events', 'sport', 'kup_bilecik', 'custom')),
    source_id   TEXT,                -- id in the source database, e.g. venues.id "node/123"
    name        TEXT NOT NULL,
    category    TEXT,
    address     TEXT,
    lat         REAL,
    lon         REAL,
    note        TEXT,
    added_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, source, source_id)
);

-- events from the other databases: "I'm going", "I've been there"
CREATE TABLE IF NOT EXISTS user_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source         TEXT NOT NULL
                   CHECK (source IN ('kup_bilecik', 'events', 'sport', 'hosted', 'custom')),
    source_id      TEXT NOT NULL,     -- kup_bilecik.events.id, events.events.id, hosted_events.id, ...
    title          TEXT NOT NULL,     -- copied so the list shows without opening the source db
    starts_at      TEXT,              -- YYYY-MM-DD HH:MM
    location_name  TEXT,
    status         TEXT NOT NULL CHECK (status IN ('interested', 'going', 'attended')),
    wants_company  INTEGER NOT NULL DEFAULT 0 CHECK (wants_company IN (0, 1)),  -- "come with me"
    spots_for_others INTEGER CHECK (spots_for_others IS NULL OR spots_for_others >= 0),
    note           TEXT,
    rating         INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),     -- after attending
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_user_events_user ON user_events(user_id, status, starts_at);

-- events created by users: picnic, concert squad, house party, ...
CREATE TABLE IF NOT EXISTS hosted_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    description   TEXT,
    category      TEXT,               -- one of CATEGORIES
    location_name TEXT,
    address       TEXT,
    lat           REAL,
    lon           REAL,
    starts_at     TEXT NOT NULL,      -- YYYY-MM-DD HH:MM
    ends_at       TEXT,
    max_guests    INTEGER CHECK (max_guests IS NULL OR max_guests > 0),
    visibility    TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'friends', 'private')),
    status        TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'cancelled', 'finished')),
    linked_source    TEXT,            -- set when the invite is for an existing event,
    linked_source_id TEXT,            -- e.g. ('kup_bilecik', '193445')
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hosted_events_host ON hosted_events(host_id, starts_at);

-- one row per person; the only table with a photo
CREATE TABLE IF NOT EXISTS people (
    id              INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,  -- same id as users
    name            TEXT UNIQUE,           -- "Mateusz Pasek" (first + second name)
    first_name      TEXT,                  -- "Mateusz"
    second_name     TEXT,                  -- "Pasek"
    username        TEXT NOT NULL UNIQUE,  -- @handle, same as users.username, kept in sync by a trigger
    email           TEXT,                  -- e.g. "wsciekly_dorsz@gmail.com"
    wiek            INTEGER CHECK (wiek IS NULL OR wiek BETWEEN 0 AND 130),  -- age in years, from birth_date
    plec            TEXT CHECK (plec IS NULL OR plec IN ('mężczyzna', 'kobieta')),
    o_mnie          TEXT,                  -- about me
    hobby           TEXT,                  -- e.g. "wspinaczka, fotografia"
    -- JSON lists below are filled by refresh_people() from the other tables
    favourite_locations TEXT,              -- favourite places: name, address
    events_going    TEXT,                  -- events I'm going to
    events_attended TEXT,                  -- events I've been to
    events_hosting  TEXT,                  -- events I'm hosting
    events          TEXT,                  -- hosted events I asked to join:
                                           -- each: event, status (pending/accepted/rejected), message, sent_at
    friends         TEXT,                  -- friends list: username, name
    friend_requests TEXT,                  -- pending friend requests: from / to, sent_at
    photo_mime      TEXT CHECK (photo_mime IS NULL OR photo_mime IN {IMAGE_TYPES}),
    photo           BLOB,                  -- may be empty for now
    CHECK ((photo IS NULL) = (photo_mime IS NULL))
);

-- one row per pair of users: pending = friend request, accepted = friends
CREATE TABLE IF NOT EXISTS friendships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    addressee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'accepted', 'rejected', 'blocked')),
    met_at       TEXT,                -- e.g. the event where they met
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    responded_at TEXT,
    CHECK (requester_id <> addressee_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_friendships_pair
    ON friendships(min(requester_id, addressee_id), max(requester_id, addressee_id));

CREATE VIEW IF NOT EXISTS friends AS
    SELECT requester_id AS user_id, addressee_id AS friend_id, responded_at AS since
    FROM friendships WHERE status = 'accepted'
    UNION ALL
    SELECT addressee_id, requester_id, responded_at
    FROM friendships WHERE status = 'accepted';

CREATE VIEW IF NOT EXISTS friend_requests AS
    SELECT id, requester_id AS from_user_id, addressee_id AS to_user_id, created_at
    FROM friendships WHERE status = 'pending';

-- whole profile in one row; list columns are JSON arrays
CREATE VIEW IF NOT EXISTS user_profiles AS
SELECT
    u.id,
    u.email,
    u.first_name,
    u.last_name                     AS second_name,
    '@' || u.username               AS username,
    (SELECT p.photo FROM people p WHERE p.id = u.id)      AS photo,
    (SELECT p.photo_mime FROM people p WHERE p.id = u.id) AS photo_mime,
    (SELECT json_group_array(json_object(
                'source', f.source, 'source_id', f.source_id, 'name', f.name, 'category', f.category,
                'address', f.address, 'lat', f.lat, 'lon', f.lon))
     FROM favourite_locations f WHERE f.user_id = u.id)                          AS favourite_locations,
    (SELECT json_group_array(json_object(
                'source', e.source, 'source_id', e.source_id, 'title', e.title, 'starts_at', e.starts_at,
                'location', e.location_name, 'wants_company', e.wants_company))
     FROM user_events e WHERE e.user_id = u.id AND e.status IN ('going', 'interested'))
                                                                                 AS events_going,
    (SELECT json_group_array(json_object(
                'source', e.source, 'source_id', e.source_id, 'title', e.title, 'starts_at', e.starts_at,
                'location', e.location_name, 'rating', e.rating))
     FROM user_events e WHERE e.user_id = u.id AND e.status = 'attended')        AS events_attended,
    (SELECT json_group_array(json_object(
                'id', h.id, 'title', h.title, 'starts_at', h.starts_at, 'location', h.location_name,
                'max_guests', h.max_guests, 'status', h.status,
                'pending_requests', (SELECT COUNT(*) FROM people p, json_each(p.events) r
                                     WHERE r.value ->> 'event' = h.title
                                       AND r.value ->> 'status' = 'pending')))
     FROM hosted_events h WHERE h.host_id = u.id)                                AS events_hosting,
    (SELECT json_group_array(json_object('id', fu.id, 'username', '@' || fu.username,
                                         'first_name', fu.first_name, 'since', fr.since))
     FROM friends fr JOIN users fu ON fu.id = fr.friend_id WHERE fr.user_id = u.id)
                                                                                 AS friends,
    (SELECT json_group_array(json_object('request_id', rq.id, 'from', '@' || ru.username,
                                         'sent_at', rq.created_at))
     FROM friend_requests rq JOIN users ru ON ru.id = rq.from_user_id WHERE rq.to_user_id = u.id)
                                                                                 AS friend_requests_received,
    (SELECT json_group_array(json_object('request_id', rq.id, 'to', '@' || ru.username,
                                         'sent_at', rq.created_at))
     FROM friend_requests rq JOIN users ru ON ru.id = rq.to_user_id WHERE rq.from_user_id = u.id)
                                                                                 AS friend_requests_sent,
    u.bio,
    u.is_public
FROM users u;

CREATE TRIGGER IF NOT EXISTS users_updated_at
AFTER UPDATE ON users FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE users SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS users_username_history
AFTER UPDATE OF username ON users FOR EACH ROW WHEN NEW.username <> OLD.username
BEGIN
    INSERT INTO username_history (user_id, old_username, new_username)
    VALUES (NEW.id, OLD.username, NEW.username);
    UPDATE people SET username = NEW.username WHERE id = NEW.id;
END;

-- every new user gets a row in people
CREATE TRIGGER IF NOT EXISTS users_people_row
AFTER INSERT ON users FOR EACH ROW
BEGIN
    INSERT INTO people (id, username, name, first_name, second_name, email, wiek, plec, o_mnie, hobby)
    VALUES (NEW.id, NEW.username, {PERSON_FIELDS}, NEW.bio,
            (SELECT group_concat(value, ', ') FROM json_each(coalesce(NEW.hobbies, '[]'))));
END;

CREATE TRIGGER IF NOT EXISTS users_people_sync
AFTER UPDATE OF first_name, last_name, email, birth_date, gender ON users FOR EACH ROW
BEGIN
    UPDATE people SET (name, first_name, second_name, email, wiek, plec) = ({PERSON_FIELDS})
    WHERE id = NEW.id;
END;
"""


def image_mime(data):
    """Returns the MIME type of image bytes, or raises ValueError if not an image."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    raise ValueError("not a supported image (JPEG, PNG, WebP, GIF)")


def check_photo(data):
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError(f"photo larger than {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    return image_mime(data)


def normalize_username(username):
    """"@Anna.K" -> "anna.k"; raises ValueError if it is not a valid handle."""
    name = username.strip().lstrip("@").lower()
    if not USERNAME_RE.match(name):
        raise ValueError(f"invalid username {username!r}: use a-z, 0-9, '.', '_' (max 30)")
    return name


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def drop_all(path=DB_PATH):
    """Empties users.db by dropping its tables (the file itself may be open elsewhere)."""
    conn = sqlite3.connect(path)
    objects = conn.execute("SELECT type, name FROM sqlite_master "
                           "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%'").fetchall()
    conn.execute("PRAGMA foreign_keys = OFF")
    for kind, name in sorted(objects, key=lambda o: o[0] != "view"):  # views first
        conn.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')
    conn.commit()
    conn.execute("VACUUM")
    conn.close()


def username_available(conn, username):
    name = normalize_username(username)
    return conn.execute("SELECT 1 FROM users WHERE username = ?", (name,)).fetchone() is None


def change_username(conn, old, new):
    old, new = normalize_username(old), normalize_username(new)
    if old != new and not username_available(conn, new):
        raise ValueError(f"@{new} is already taken")
    cur = conn.execute("UPDATE users SET username = ? WHERE username = ?", (new, old))
    if cur.rowcount == 0:
        raise ValueError(f"no user @{old}")


def add_user(conn, email, username, **fields):
    """Inserts a user. List fields (hobbies, interests, languages) may be Python lists."""
    for key in ("hobbies", "interests", "languages"):
        if isinstance(fields.get(key), list):
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    cols = ["email", "username", *fields]
    cur = conn.execute(
        f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [email.strip().lower(), normalize_username(username), *fields.values()],
    )
    return cur.lastrowid


def set_photo(conn, username, data):
    mime = check_photo(data)
    cur = conn.execute("UPDATE people SET photo = ?, photo_mime = ? WHERE username = ?",
                       (data, mime, normalize_username(username)))
    if cur.rowcount == 0:
        raise ValueError(f"no user @{username}")


def refresh_people(conn):
    """Fills the JSON list columns of people from the other tables."""
    conn.execute("""
        UPDATE people SET
            favourite_locations = (
                SELECT json_group_array(json_object('name', name, 'address', address))
                FROM favourite_locations WHERE user_id = people.id),
            events_going = (
                SELECT json_group_array(json_object('title', title, 'starts_at', starts_at, 'location', location_name))
                FROM user_events WHERE user_id = people.id AND status IN ('going', 'interested')),
            events_attended = (
                SELECT json_group_array(json_object('title', title, 'starts_at', starts_at, 'location', location_name))
                FROM user_events WHERE user_id = people.id AND status = 'attended'),
            events_hosting = (
                SELECT json_group_array(json_object('title', title, 'starts_at', starts_at,
                                                    'location', location_name, 'max_guests', max_guests))
                FROM hosted_events WHERE host_id = people.id),
            friends = (
                SELECT json_group_array(json_object('username', '@' || p.username, 'name', p.name))
                FROM friends f JOIN people p ON p.id = f.friend_id WHERE f.user_id = people.id),
            friend_requests = (
                SELECT json_group_array(json_object(
                           'from', '@' || (SELECT username FROM people WHERE id = r.from_user_id),
                           'to', '@' || (SELECT username FROM people WHERE id = r.to_user_id),
                           'sent_at', r.created_at))
                FROM friend_requests r WHERE people.id IN (r.from_user_id, r.to_user_id))""")


def placeholder_png(top, bottom, size=96):
    """Square PNG split diagonally into two colours, used as a mock avatar."""
    rows = b"".join(
        b"\x00" + b"".join(bytes(top if x > y else bottom) for x in range(size))
        for y in range(size)
    )

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- mock data

DEMO_USERS = [
    dict(email="anna.kowalska@example.com", username="anna.kowalska", first_name="Anna",
         last_name="Kowalska", birth_date="1998-04-12", gender="female", pronouns="she/her",
         district="Mokotów", occupation="UX designer", nationality="PL", new_in_city=1,
         bio="Przeprowadziłam się z Gdańska, szukam ekipy na koncerty i pikniki.",
         hobbies=["wspinaczka", "fotografia analogowa", "ceramika"],
         interests=["music", "nightlife", "festivals", "exhibitions"], languages=["pl", "en"],
         instagram="https://instagram.com/anna.kowalska", spotify="https://open.spotify.com/user/annak",
         looking_for="towarzystwo na koncerty", preferred_squad_size=4, is_verified=1),
    dict(email="tomek.runs@example.com", username="tomek_runs", first_name="Tomasz",
         last_name="Wiśniewski", birth_date="1993-09-30", gender="male", pronouns="he/him",
         district="Wola", occupation="księgowy", nationality="PL",
         bio="Parkrun co sobotę, po pracy bulwary. Biegam 5:30/km.",
         hobbies=["bieganie", "kawa speciality", "rower"], interests=["running", "sports"],
         languages=["pl", "en"], looking_for="ekipa na parkrun w sobotę", preferred_squad_size=6),
    dict(email="li.wei@example.com", username="li.wei", first_name="Li", last_name="Wei",
         birth_date="2001-02-18", nationality="CN", university="Uniwersytet Warszawski",
         district="Śródmieście", new_in_city=1, languages=["en", "zh"],
         bio="Erasmus student, learning Polish. Looking for a language exchange!",
         hobbies=["kaligrafia", "gotowanie"], interests=["meetups", "study_buddies", "culture"],
         looking_for="language exchange PL/EN/ZH", preferred_squad_size=3),
    dict(email="kasia.nowak@example.com", username="kasia_nowak", first_name="Katarzyna",
         last_name="Nowak", display_name="Kasia", birth_date="1996-11-03", gender="female",
         district="Praga-Północ", occupation="aktorka", nationality="PL",
         bio="Teatr, impro i dobre wino. Zawsze mam wolną wejściówkę.",
         hobbies=["impro", "wino", "joga"], interests=["theatre", "film", "culture"],
         languages=["pl", "en", "fr"], instagram="https://instagram.com/kasia_nowak",
         looking_for="ktoś na premiery teatralne"),
    dict(email="jakub.w@example.com", username="kuba.dev", first_name="Jakub",
         last_name="Wójcik", birth_date="1995-06-21", gender="male", district="Ochota",
         occupation="backend developer", nationality="PL",
         hobbies=["planszówki", "elektronika", "techno"], interests=["meetups", "nightlife", "music"],
         languages=["pl", "en"], github="https://github.com/kuba-dev",
         linkedin="https://linkedin.com/in/kuba-dev", looking_for="squad na techno w Smolnej"),
    dict(email="maria.garcia@example.com", username="maria.garcia", first_name="María",
         last_name="García", birth_date="1999-08-09", gender="female", pronouns="she/her",
         nationality="ES", district="Powiśle", occupation="marketing specialist", new_in_city=1,
         bio="Hola! Madrileña en Varsovia. Busco amigos para salir.",
         hobbies=["salsa", "podróże", "fotografia"], interests=["nightlife", "festivals", "markets"],
         languages=["es", "en", "pl"], instagram="https://instagram.com/maria.garcia.waw",
         tiktok="https://tiktok.com/@mariagarcia"),
    dict(email="zuza.yoga@example.com", username="zuza.yoga", first_name="Zuzanna",
         last_name="Lewandowska", birth_date="1990-01-27", gender="female", district="Żoliborz",
         occupation="instruktorka jogi", nationality="PL", is_verified=1,
         bio="Joga o wschodzie słońca w Łazienkach, każdy poziom mile widziany.",
         hobbies=["joga", "medytacja", "grzybobranie"], interests=["yoga", "grzybki", "running"],
         languages=["pl", "en"], website="https://example.com/zuza-yoga"),
    dict(email="piotr.mazur@example.com", username="piotr_mazur", first_name="Piotr",
         last_name="Mazur", birth_date="1988-12-14", gender="male", district="Bielany",
         occupation="lekarz", nationality="PL",
         hobbies=["piłka nożna", "jazz", "szachy"], interests=["sports", "music"],
         languages=["pl", "de"], facebook="https://facebook.com/piotr.mazur",
         looking_for="ktoś na mecz Legii"),
    dict(email="emma.jones@example.com", username="emma_jones", first_name="Emma",
         last_name="Jones", birth_date="1997-05-05", gender="female", pronouns="she/her",
         nationality="GB", district="Śródmieście", occupation="English teacher", new_in_city=1,
         bio="Brit in Warsaw. Board games, pub quizzes and cheap theatre tickets.",
         hobbies=["planszówki", "pub quiz", "czytanie"], interests=["theatre", "meetups", "film"],
         languages=["en"], preferred_squad_size=4),
    dict(email="olek.k@example.com", username="olek", first_name="Aleksander",
         last_name="Kamiński", birth_date="2003-03-15", gender="male", district="Ursynów",
         university="Politechnika Warszawska", nationality="PL",
         hobbies=["koszykówka", "gry"], interests=["study_buddies", "sports", "film"],
         languages=["pl", "en"], looking_for="study buddy do analizy matematycznej"),
    dict(email="minimal@example.com", username="minimal_user"),  # only the required fields
]

AVATAR_COLOURS = [
    ((231, 111, 81), (244, 162, 97)), ((42, 157, 143), (38, 70, 83)), ((233, 196, 106), (231, 111, 81)),
    ((131, 56, 236), (58, 134, 255)), ((255, 0, 110), (251, 86, 7)), ((6, 214, 160), (17, 138, 178)),
    ((239, 71, 111), (255, 209, 102)), ((7, 59, 76), (17, 138, 178)), ((106, 76, 147), (25, 130, 196)),
    ((138, 201, 38), (25, 130, 196)),
]

CUSTOM_PLACES = [
    ("Pole Mokotowskie", "park", "Pole Mokotowskie, Warszawa", 52.2132, 21.0005),
    ("Bulwary Wiślane", "park", "Bulwar Flotylli Wiślanej, Warszawa", 52.2420, 21.0290),
    ("Łazienki Królewskie", "park", "Agrykoli 1, 00-460 Warszawa", 52.2150, 21.0350),
    ("Plac Zbawiciela", "square", "Plac Zbawiciela, Warszawa", 52.2196, 21.0185),
    ("Hala Koszyki", "food_hall", "Koszykowa 63, 00-667 Warszawa", 52.2224, 21.0123),
]

FALLBACK_VENUES = [("custom-1", "Teatr Polski", "theatre", "Karasia 2, Warszawa", 52.2394, 21.0145),
                   ("custom-2", "Kino Muranów", "cinema", "Andersa 5, Warszawa", 52.2460, 20.9980)]


def read_only(path, sql, params=()):
    """Rows from another database, or [] if it is missing (never creates the file)."""
    if not path.exists():
        return []
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def at(days, hour, minute=0):
    return (datetime.combine(date.today() + timedelta(days=days), datetime.min.time())
            + timedelta(hours=hour, minutes=minute)).strftime("%Y-%m-%d %H:%M")


def seed_demo(conn):
    rnd = random.Random(42)
    ids = {}
    for i, user in enumerate(DEMO_USERS):
        user = dict(user)
        username = user.pop("username")
        if username != "minimal_user":
            user["last_seen_at"] = at(-rnd.randint(0, 3), rnd.randint(8, 23))
        ids[username] = add_user(conn, user.pop("email"), username, **user)
        if username != "minimal_user":
            set_photo(conn, username, placeholder_png(*AVATAR_COLOURS[i % len(AVATAR_COLOURS)]))
    u = ids  # shorter

    # favourite locations: real venues from street_gl.db + well-known custom places
    venues = read_only(STREET_GL_DB, "SELECT id, name, category, location, lat, lon FROM venues "
                                     "WHERE name IS NOT NULL AND lat IS NOT NULL ORDER BY id")
    venues = venues or FALLBACK_VENUES
    for username, user_id in u.items():
        if username == "minimal_user":
            continue
        for v in rnd.sample(venues, min(3, len(venues))):
            conn.execute("INSERT OR IGNORE INTO favourite_locations (user_id, source, source_id, name, category, "
                         "address, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (user_id, "street_gl" if venues is not FALLBACK_VENUES else "custom", *v))
        name, cat, addr, lat, lon = rnd.choice(CUSTOM_PLACES)
        conn.execute("INSERT OR IGNORE INTO favourite_locations (user_id, source, source_id, name, category, "
                     "address, lat, lon, note) VALUES (?, 'custom', ?, ?, ?, ?, ?, ?, ?)",
                     (user_id, name, name, cat, addr, lat, lon, "ulubione miejsce na spotkania"))

    # events I'm going to: upcoming Warsaw events from kup_bilecik.db
    upcoming = read_only(KUP_BILECIK_DB, "SELECT id, name, date || ' ' || coalesce(time, '00:00'), location "
                                         "FROM events WHERE city = 'Warszawa' AND date >= date('now') "
                                         "ORDER BY date, time LIMIT 60")
    # events I've been to: finished events from the city calendar (events.db)
    past = read_only(EVENTS_DB, "SELECT id, title, data || ' ' || coalesce(start_time, '00:00'), place_name "
                                "FROM events WHERE data < date('now') ORDER BY data DESC LIMIT 40")
    if not upcoming:
        upcoming = [(f"mock-{d}", f"Koncert #{d}", at(d, 20), "Klub Hydrozagadka") for d in range(1, 15)]
    if not past:
        past = [(f"mock-past-{d}", f"Wystawa #{d}", at(-d, 12), "Zachęta") for d in range(1, 15)]

    def add_event(user_id, source, row, status, **extra):
        cols = ["user_id", "source", "source_id", "title", "starts_at", "location_name", "status", *extra]
        conn.execute(f"INSERT OR IGNORE INTO user_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     (user_id, source, str(row[0]), row[1], row[2], row[3], status, *extra.values()))

    shared = upcoming[0]  # several people going to the same event -> "come with me" demo
    for username in ("anna.kowalska", "maria.garcia", "kuba.dev", "emma_jones"):
        add_event(u[username], "kup_bilecik", shared, "going", wants_company=1, spots_for_others=2,
                  note="Szukam ekipy, potem afterparty?")
    for username, user_id in u.items():
        if username == "minimal_user":
            continue
        for row in rnd.sample(upcoming[1:], 2):
            add_event(user_id, "kup_bilecik", row, rnd.choice(["going", "going", "interested"]),
                      wants_company=rnd.randint(0, 1))
        for row in rnd.sample(past, rnd.randint(1, 3)):
            add_event(user_id, "events", row, "attended", rating=rnd.randint(3, 5))

    # events I'm hosting
    hosted = [
        ("anna.kowalska", "Piknik na Polu Mokotowskim", "Kocyk, gry, wino bezalkoholowe. Każdy przynosi coś do jedzenia!",
         "festivals", "Pole Mokotowskie", "Pole Mokotowskie, Warszawa", 52.2132, 21.0005, at(1, 16), at(1, 20), 12, "public"),
        ("tomek_runs", "Sobotni bieg bulwarami 8 km", "Spokojne tempo 6:00/km, potem kawa na Powiślu.",
         "running", "Bulwary Wiślane", "Bulwar Flotylli Wiślanej, Warszawa", 52.2420, 21.0290, at(2, 9), at(2, 11), 15, "public"),
        ("zuza.yoga", "Joga o wschodzie słońca", "Weź matę i wodę. Poziom dowolny.",
         "yoga", "Łazienki Królewskie", "Agrykoli 1, 00-460 Warszawa", 52.2150, 21.0350, at(3, 6, 30), at(3, 7, 30), 20, "public"),
        ("kuba.dev", "Planszówki i pizza", "Mam Wsiąść do Pociągu, Diuna Imperium i Codenames.",
         "meetups", "Mieszkanie na Ochocie", "Grójecka (dokładny adres po akceptacji)", 52.2190, 20.9850, at(4, 19), at(4, 23), 6, "friends"),
        ("li.wei", "Language exchange PL/EN/ZH", "Pół godziny po polsku, pół po angielsku.",
         "meetups", "Hala Koszyki", "Koszykowa 63, 00-667 Warszawa", 52.2224, 21.0123, at(5, 18), at(5, 20), 8, "public"),
        ("anna.kowalska", "Ekipa na koncert", "Idę na ten koncert, mam 2 wolne miejsca w ekipie.",
         "music", shared[3], None, None, None, shared[2], None, 3, "public"),
        ("emma_jones", "Pub quiz squad", "We need 2 more for our pub quiz team!",
         "meetups", "Pub Lolek", "Rokitnicka 20, Warszawa", 52.2120, 20.9940, at(-3, 19), at(-3, 22), 4, "public"),
    ]
    event_ids = {}
    for host, title, desc, cat, loc, addr, lat, lon, start, end, max_g, vis in hosted:
        linked = ("kup_bilecik", str(shared[0])) if title == "Ekipa na koncert" else (None, None)
        status = "finished" if start < at(0, 0) else "planned"
        cur = conn.execute(
            "INSERT INTO hosted_events (host_id, title, description, category, location_name, address, lat, lon, "
            "starts_at, ends_at, max_guests, visibility, status, linked_source, linked_source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (u[host], title, desc, cat, loc, addr, lat, lon, start, end, max_g, vis, status, *linked))
        event_ids[title] = (cur.lastrowid, title, start, loc)

    requests = [
        ("Piknik na Polu Mokotowskim", "maria.garcia", "accepted", "Przyniosę tortillę!"),
        ("Piknik na Polu Mokotowskim", "li.wei", "accepted", "Can I join? I'll bring dumplings."),
        ("Piknik na Polu Mokotowskim", "olek", "pending", "Hej, mogę wpaść z kolegą?"),
        ("Sobotni bieg bulwarami 8 km", "piotr_mazur", "accepted", None),
        ("Sobotni bieg bulwarami 8 km", "zuza.yoga", "pending", "Dołączę jako rozgrzewka przed jogą :)"),
        ("Joga o wschodzie słońca", "anna.kowalska", "accepted", None),
        ("Joga o wschodzie słońca", "kasia_nowak", "accepted", "Pierwszy raz, mogę?"),
        ("Planszówki i pizza", "emma_jones", "accepted", "I love Codenames!"),
        ("Planszówki i pizza", "olek", "rejected", None),
        ("Language exchange PL/EN/ZH", "emma_jones", "pending", "I'd love to practise Polish."),
        ("Language exchange PL/EN/ZH", "maria.garcia", "pending", None),
        ("Ekipa na koncert", "kasia_nowak", "pending", "Też idę, chętnie z wami!"),
        ("Pub quiz squad", "kuba.dev", "accepted", None),
        ("Pub quiz squad", "olek", "accepted", None),
    ]
    asked = {username: [] for username in u}
    for title, username, status, message in requests:
        start = event_ids[title][2]
        if status == "accepted":
            add_event(u[username], "hosted", event_ids[title], "attended" if start < at(0, 0) else "going")
        asked[username].append({"event": title, "status": status, "message": message, "sent_at": at(-1, 12)})
    for username, events in asked.items():
        conn.execute("UPDATE people SET events = ? WHERE id = ?",
                     (json.dumps(events, ensure_ascii=False), u[username]))


    # friends and friend requests
    friendships = [
        ("anna.kowalska", "maria.garcia", "accepted", "Piknik na Polu Mokotowskim"),
        ("anna.kowalska", "zuza.yoga", "accepted", "Joga o wschodzie słońca"),
        ("anna.kowalska", "kuba.dev", "accepted", None),
        ("maria.garcia", "li.wei", "accepted", None),
        ("emma_jones", "kuba.dev", "accepted", "Pub quiz squad"),
        ("emma_jones", "olek", "accepted", "Pub quiz squad"),
        ("tomek_runs", "piotr_mazur", "accepted", "Sobotni bieg bulwarami 8 km"),
        ("kasia_nowak", "zuza.yoga", "accepted", None),
        ("li.wei", "anna.kowalska", "pending", None),
        ("olek", "kasia_nowak", "pending", None),
        ("piotr_mazur", "anna.kowalska", "pending", None),
        ("emma_jones", "maria.garcia", "pending", None),
        ("olek", "maria.garcia", "rejected", None),
    ]
    for a, b, status, met_at in friendships:
        conn.execute("INSERT INTO friendships (requester_id, addressee_id, status, met_at, created_at, responded_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     (u[a], u[b], status, met_at, at(-rnd.randint(5, 40), 12),
                      None if status == "pending" else at(-rnd.randint(0, 4), 18)))

    conn.execute("UPDATE users SET password_hash = 'demo-not-a-real-hash' WHERE username <> 'minimal_user'")


def export_people(conn, path=PEOPLE_DB_PATH):
    """Writes the people table on its own to people.db (replacing the old copy)."""
    create = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'people'").fetchone()[0]
    create = create.replace("REFERENCES users(id) ON DELETE CASCADE", "")  # users is not in people.db
    rows = conn.execute("SELECT * FROM people").fetchall()
    out = sqlite3.connect(path)
    with out:
        out.execute("DROP TABLE IF EXISTS people")
        out.execute(create)
        if rows:
            out.executemany(f"INSERT INTO people VALUES ({', '.join('?' * len(rows[0]))})", rows)
    out.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="add mock users and their data")
    parser.add_argument("--reset", action="store_true", help="drop all tables in users.db first")
    parser.add_argument("--photo", nargs=2, metavar=("USERNAME", "FILE"), help="set a user's photo (in people)")
    parser.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"), help="change a user's @username")
    args = parser.parse_args()

    if args.reset:
        drop_all()
    conn = connect()
    with conn:
        if args.demo:
            if conn.execute("SELECT 1 FROM users WHERE username = 'anna.kowalska'").fetchone():
                print("demo data already present (use --reset --demo to recreate)")
            else:
                seed_demo(conn)
        if args.photo:
            username, file = args.photo
            set_photo(conn, username, Path(file).read_bytes())
        if args.rename:
            change_username(conn, *args.rename)
        refresh_people(conn)
    export_people(conn)

    for table in ("users", "people", "favourite_locations", "user_events", "hosted_events", "friendships"):
        print(f"  {table}: {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
